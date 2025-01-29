#!/usr/bin/env python3
import cdk_nag
from aws_cdk import Aspects
import aws_cdk as cdk
from aws_bedrock_langchain_python_cdk.aws_bedrock_langchain_python_cdk_stack import AwsBedrockLangchainPythonCdkStack
from aws_bedrock_langchain_python_cdk.aws_bedrock_langchain_codepipeline_stack import AwsBedrockLangchainCodePipelineStack

app = cdk.App()


aws_bedrock_langchain_stack = AwsBedrockLangchainPythonCdkStack(app, "AwsBedrockLangchainPythonCdkStack")
aws_bedrock_langchain_codepipeline_stack = AwsBedrockLangchainCodePipelineStack(app, "AwsBedrockLangchainCodePipeline")

Aspects.of(app).add(cdk_nag.AwsSolutionsChecks(reports=True, verbose=True))

app.synth()
