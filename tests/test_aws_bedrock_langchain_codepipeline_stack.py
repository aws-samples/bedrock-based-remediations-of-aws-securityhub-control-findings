import aws_cdk as cdk
import aws_cdk.assertions as assertions
import aws_cdk.aws_codecommit as codecommit
from aws_bedrock_langchain_python_cdk.aws_bedrock_langchain_codepipeline_stack import AwsBedrockLangchainCodePipelineStack

def test_codepipeline_created():
    app = cdk.App()
    stack = cdk.Stack(app, "TestStack")
    codecommit_repo = codecommit.Repository.from_repository_name(stack, "CodeCommitRepo", "genai_remediations")
    pipeline_stack = AwsBedrockLangchainCodePipelineStack(stack, "PipelineStack", codecommit_repo=codecommit_repo)

    pipeline = pipeline_stack.node.find_child("BedrockLangchainPipeline")
    assert pipeline is not None, "CodePipeline should be created"

    source_stage = pipeline.node.find_child("Source")
    assert source_stage is not None, "Source stage should be created"

    source_action = source_stage.node.find_child("CodeCommit Source")
    assert source_action is not None, "CodeCommit source action should be created"

    deploy_stage = pipeline.node.find_child("Deploy")
    assert deploy_stage is not None, "Deploy stage should be created"

    cloudformation_action = deploy_stage.node.find_child("CloudFormation StackSet")
    assert cloudformation_action is not None, "CloudFormation StackSet action should be created"
