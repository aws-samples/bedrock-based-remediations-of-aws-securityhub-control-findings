import aws_cdk as cdk
import aws_cdk.assertions as assertions
from aws_bedrock_langchain_python_cdk.aws_bedrock_langchain_codepipeline_stack import AwsBedrockLangchainCodePipelineStack

def test_codepipeline_created():
    app = cdk.App(context={
        "GITHUB_OWNER": "test-owner",
        "GITHUB_REPO": "test-repo",
        "GITHUB_BRANCH": "main"
    })
    stack = cdk.Stack(app, "TestStack")
    pipeline_stack = AwsBedrockLangchainCodePipelineStack(stack, "PipelineStack")

    template = assertions.Template.from_stack(pipeline_stack)

    template.has_resource_properties("AWS::CodePipeline::Pipeline", {
        "Stages": assertions.Match.array_with([{
            "Name": "Source",
            "Actions": assertions.Match.array_with([{
                "ActionTypeId": {
                    "Provider": "GitHub"
                },
                "Configuration": {
                    "Owner": "test-owner",
                    "Repo": "test-repo",
                    "Branch": "main"
                }
            }])
        }])
    })

    # Additional assertions for ValidateCloudFormation and BuildAndDeploy stages
    template.has_resource_properties("AWS::CodeBuild::Project", {
        "Name": "ValidateCloudFormation"
    })
    template.has_resource_properties("AWS::CodeBuild::Project", {
        "Name": "BuildAndDeploy"
    })

    cloudformation_action = deploy_stage.node.find_child("CloudFormation StackSet")
    assert cloudformation_action is not None, "CloudFormation StackSet action should be created"
