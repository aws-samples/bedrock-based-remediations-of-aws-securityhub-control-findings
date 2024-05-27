import aws_cdk as cdk
from aws_cdk import (
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as codepipeline_actions,
    aws_codecommit as codecommit,
    aws_codebuild as codebuild
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
            })
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
        deploy_project = codebuild.PipelineProject(self, 'DeployProject',
            build_spec=codebuild.BuildSpec.from_object({
                'version': '0.2',
                'phases': {
                    'build': {
                        'commands': [
                            'for file in $(find deploy -name "*.yaml"); do STACK_NAME=$(basename $file .yaml); aws cloudformation deploy --template-file $file --stack-name $STACK_NAME --parameter-overrides file://deploy/parameters/$STACK_NAME-params.json || aws cloudformation deploy --template-file $file --stack-name $STACK_NAME; done'
                        ]
                    }
                }
            })
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
