import aws_cdk as cdk
from aws_cdk import (
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as codepipeline_actions,
    aws_codecommit as codecommit,
    aws_codebuild as codebuild,
    aws_iam as iam
    )
from constructs import Construct
from cdk_nag import NagSuppressions

class AwsBedrockLangchainCodePipelineStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, codecommit_repo: codecommit.Repository, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get params from context
        notification_emails = self.node.try_get_context("NOTIFICATION_EMAILS")
        
        # Define the source stage
        source_output = codepipeline.Artifact("SourceArtifact")
        source_stage = codepipeline.StageProps(
            stage_name="Source",
            actions=[
                codepipeline_actions.CodeCommitSourceAction(
                    action_name="CodeCommitSource",
                    repository=codecommit_repo,
                    output=source_output,
                    branch='main',
                )
            ],
        )
        
        stack_name = "SecurityHubRemediationWorkflow"
        change_set_name = "StagedChangeSet"
        # Import required libraries
        import json
        import os
    
        # Get CloudFormation execution role ARN from context
        cfn_exec_role_arn = self.node.try_get_context("CFN_EXEC_ROLE_ARN")
        if cfn_exec_role_arn is None:
            cfn_exec_role_arn = ""

        # Get Workload account IDs from context
        workload_accounts = self.node.try_get_context("WORKLOAD_ACCOUNTS")
        if workload_accounts is None:
            workload_accounts = []
            
        # Validation CodeBuild project
        validate_project = codebuild.PipelineProject(self, 'ValidateProject',
            build_spec=codebuild.BuildSpec.from_object({
                'version': '0.2',
                'phases': {
                    'build': {
                        'commands': [
                            'for file in $(find deploy -name "*.yaml"); do aws cloudformation validate-template --template-body file://$file; done'
                        ]
                    }
                }
            }),
            role=iam.Role(self, "ValidateProjectRole", assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
                          # Create inline policy to allow codebuild to run validate-template command 
                          inline_policies={
                            "ValidateTemplatePolicy": iam.PolicyDocument(statements=[
                                iam.PolicyStatement(
                                    effect=iam.Effect.ALLOW,
                                    actions=["cloudformation:ValidateTemplate"],
                                    resources=["*"]
                                )
                            ])
                          }
                        )
        )

        # Validation stage
        validation_stage = codepipeline.StageProps(
            stage_name="Validate",
            actions=[
                codepipeline_actions.CodeBuildAction(
                    action_name="ValidateTemplates",
                    project=validate_project,
                    input=source_output,
                    outputs=[codepipeline.Artifact()]
                )
            ],
        )

        # Manual approval stage
        approval_stage = codepipeline.StageProps(
            stage_name="Approve",
            actions=[
                codepipeline_actions.ManualApprovalAction(
                    action_name="Approve",
                    additional_information="Approve the deployment of the stack.",
                    notify_emails = notification_emails
                )
            ],
        )

        # Deploy CodeBuild project
        deploy_project = codebuild.PipelineProject(
            self, 'DeployProject',
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "phases": {
                    "pre_build": {
                        "commands": [
                            "echo \"Preparing to deploy CloudFormation stacks...\""
                        ]
                    },
                    "build": {
                        "commands": [
                            "set -e && for file in $(find deploy -name \"*.yaml\"); do STACK_NAME=$(basename $file .yaml); if [ -z \"$CFN_EXEC_ROLE_ARN\" ]; then echo \"Deploying stack $STACK_NAME directly...\"; aws cloudformation deploy --template-file $file --stack-name $STACK_NAME --parameter-overrides file://deploy/parameters/$STACK_NAME-params.json || exit 1; else echo \"Deploying stack $STACK_NAME as a StackSet...\"; STACK_SET_NAME=RemediationAutomate-$STACK_NAME; aws cloudformation create-stack-set --stack-set-name $STACK_SET_NAME --template-body file://$file --capabilities CAPABILITY_NAMED_IAM --execution-role-name $CFN_EXEC_ROLE_NAME || exit 1; aws cloudformation create-stack-instances --stack-set-name $STACK_SET_NAME --accounts ${WORKLOAD_ACCOUNTS} --regions us-east-1 || exit 1; fi; done; echo \"CloudFormation stack deployment complete.\""
                        ]
                    },
                    "post_build": {
                        "commands": [
                            "if [ $? -ne 0 ]; then echo \"Error occurred during CloudFormation stack deployment.\"; exit 1; fi"
                        ]
                    }
                }
            }),
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_5_0
            ),
            role=iam.Role(
                self, "DeployProjectRole",
                assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
                # Create inline policy to allow codebuild to run deploy command as well as create change set
                inline_policies={
                    "DeployPolicy": iam.PolicyDocument(
                        statements=[
                            iam.PolicyStatement(
                                effect=iam.Effect.ALLOW,
                                actions=["cloudformation:*", "ssm:*", "s3:*" ],
                                resources=["*"]
                            )
                        ]
                    )
                }
            ),
            environment_variables={
                "CFN_EXEC_ROLE_ARN": codebuild.BuildEnvironmentVariable(value=cfn_exec_role_arn),
                "WORKLOAD_ACCOUNTS": codebuild.BuildEnvironmentVariable(value=workload_accounts)
            }
        )

        # Define the deploy stage
        deploy_stage = codepipeline.StageProps(
            stage_name="Deploy",
            actions=[
                codepipeline_actions.CodeBuildAction(
                    action_name="DeployStack",
                    project=deploy_project,
                    input=source_output,
                    outputs=[codepipeline.Artifact()]
                )
            ],
        )

        # Create the CodePipeline
        codepipeline.Pipeline(
            self,
            "BedrockLangchainPipeline",
            pipeline_name="BedrockLangchainPipeline",
            stages=[
                source_stage,
                validation_stage,
                approval_stage,
                deploy_stage
            ]
        )

        # Add NagSuppressions for identified errors in CodePipeline stack
        NagSuppressions.add_stack_suppressions(self, [
                                            {
                                                "id": 'AwsSolutions-IAM5',
                                                "reason": 'CodePipeline needs wildcard permissions to create change sets and execute changes'
                                            },
                                            {
                                                "id": "AwsSolutions-KMS5",
                                                "reason": "No need for granular rotation, just a single key used for demo purposes"
                                            },
                                            {
                                                "id": "AwsSolutions-S1",
                                                "reason": "Access logs not required for demo"
                                            },
                                                                                        {
                                                "id": "AwsSolutions-SNS2",
                                                "reason": "Using high level construct for demo"
                                            },
                                                                                        {
                                                "id": "AwsSolutions-SNS3",
                                                "reason": "Using construct for demo"
                                            }
                                        ])
