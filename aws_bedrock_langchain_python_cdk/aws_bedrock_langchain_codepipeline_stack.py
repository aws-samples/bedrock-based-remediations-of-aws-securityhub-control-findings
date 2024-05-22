import aws_cdk as cdk
from aws_cdk import (
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as codepipeline_actions,
    aws_codecommit as codecommit
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
                    trigger=codepipeline_actions.CodeCommitTrigger.NONE
                )
            ],
        )
        
        stack_name = "SecurityHubRemediationWorkflow"
        change_set_name = "StagedChangeSet"

        # Define the deploy stage
        deploy_stage = codepipeline.StageProps(
            stage_name="Deploy",
            actions=[
                codepipeline_actions.CloudFormationCreateReplaceChangeSetAction(
                    action_name="PrepareChanges",
                    stack_name=stack_name,
                    change_set_name=change_set_name,
                    admin_permissions=True,
                    template_path=source_output.at_path("deploy/*.yaml"),
                    run_order = 1
                ),
                codepipeline_actions.ManualApprovalAction(
                    action_name="ApproveChanges",
                    additional_information="Approve the changes to the stack.",
                    notify_emails = notification_emails,
                    run_order = 3
                ),
                codepipeline_actions.CloudFormationExecuteChangeSetAction(
                    action_name="ExecuteChanges",
                    stack_name=stack_name,
                    change_set_name=change_set_name,
                    run_order = 3
                )
            ],
        )

        # Create the CodePipeline
        codepipeline.Pipeline(
            self,
            "BedrockLangchainPipeline",
            pipeline_name="BedrockLangchainPipeline",
            stages=[source_stage, deploy_stage],
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
