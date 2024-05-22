import aws_cdk as core
import aws_cdk.assertions as assertions
from cdk_nag import NagSuppressions

from aws_bedrock_langchain_python_cdk.aws_bedrock_langchain_python_cdk_stack import AwsBedrockLangchainPythonCdkStack

def test_stack_created_with_model_id_and_kb_id():
    app = core.App()
    model_id = "example_model_id"
    kb_id = "example_kb_id"
    stack = AwsBedrockLangchainPythonCdkStack(app, "AwsBedrockLangchainPythonCdkStack", model_id=model_id, kb_id=kb_id)
    assert stack.model_id == model_id
    assert stack.kb_id == kb_id

def test_nag_suppressions_applied():
    app = core.App()
    model_id = "example_model_id"
    kb_id = "example_kb_id"
    stack = AwsBedrockLangchainPythonCdkStack(app, "AwsBedrockLangchainPythonCdkStack", model_id=model_id, kb_id=kb_id)

    # Test case 1: cdk-nag report before applying NagSuppressions
    cdk_nag_report = NagSuppressions.get_report(stack)
    assert len(cdk_nag_report.get_warnings()) > 0, "Expected warnings before applying NagSuppressions"

    # Test case 2: cdk-nag report after applying NagSuppressions
    NagSuppressions.apply_suppressions(stack)
    cdk_nag_report = NagSuppressions.get_report(stack)
    assert len(cdk_nag_report.get_warnings()) == 0, "No warnings expected after applying NagSuppressions"
