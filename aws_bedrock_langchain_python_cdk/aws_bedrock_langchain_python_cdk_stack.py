from aws_cdk import (
    Stack,
    Duration,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_lambda_python_alpha as _alambda,
    SecretValue
)
from constructs import Construct
from cdk_nag import NagSuppressions

class AwsBedrockLangchainPythonCdkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Get params from context
        bedrock_agent_arn = self.node.try_get_context("BEDROCK_AGENT_ARN")
        kb_id = self.node.try_get_context("KB_ID")
        model_id = self.node.try_get_context("MODEL_ID")
        github_repo = self.node.try_get_context("GITHUB_REPO")
        github_owner = self.node.try_get_context("GITHUB_OWNER")

        bedrock_policy = iam.PolicyStatement(
            effect= iam.Effect.ALLOW,
            actions= [
                "bedrock:*",   
            ],
            resources= ["*"]
        )
        
        lambda_role = iam.Role(
            self,
            "LambdaRole",
            assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'),
            description="Role to access Bedrock service by lambda",
            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name(
                                    'service-role/AWSLambdaBasicExecutionRole'),
                                ]
        )

        # attach policy to role
        lambda_role.add_to_principal_policy(bedrock_policy)
        
        # attach policy to allow secrets manager secret retrieval for github-token
        lambda_role.add_to_principal_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["secretsmanager:GetSecretValue"],
            resources=["arn:aws:secretsmanager:*"]
        ))

        boto3_lambda_layer = _alambda.PythonLayerVersion(self, 
                                                    'boto3-lambda-layer',
                                                    entry = './aws_bedrock_langchain_python_cdk/lambda/layer/boto3_latest/',
                                                    compatible_architectures=[_lambda.Architecture.ARM_64],
                                                    compatible_runtimes=[_lambda.Runtime.PYTHON_3_11],
        )

        langchain_lambda_layer = _alambda.PythonLayerVersion(self, 
                                                    'langchain-lambda-layer',
                                                    entry = './aws_bedrock_langchain_python_cdk/lambda/layer/langchain_latest/',
                                                    compatible_architectures=[_lambda.Architecture.ARM_64],
                                                    compatible_runtimes=[_lambda.Runtime.PYTHON_3_11 ],
        )

        langchain_bedrock_lambda = _lambda.Function(
            self,
            "langchain-bedrock-lambda",
            handler="index.lambda_handler",
            code=_lambda.Code.from_asset("./aws_bedrock_langchain_python_cdk/lambda/code/langchain/"),
            runtime=_lambda.Runtime.PYTHON_3_11,
            architecture=_lambda.Architecture.ARM_64,
            role=lambda_role,
            layers=[
                boto3_lambda_layer,
                langchain_lambda_layer
            ],
            timeout=Duration.seconds(900),
            memory_size=1024,
            environment={
                "MODEL_ID": model_id,
                "KB_ID": kb_id,
                "GITHUB_REPO": github_repo,
                "GITHUB_OWNER": github_owner
            }
        )
        
        # Add lambda permission to allow bedrock to invoke the function
        langchain_bedrock_lambda.add_permission(
            "bedrock-permission",
            principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_account=self.account,
            source_arn=bedrock_agent_arn,
        )
        
        # CDK NAG suppression
        NagSuppressions.add_stack_suppressions(self, [
                                            {
                                                "id": 'AwsSolutions-IAM4',
                                                "reason": 'Lambda execution policy for custom resources created by higher level CDK constructs',
                                                "appliesTo": [
                                                        'Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole',
                                                    ],
                                            }])
        NagSuppressions.add_resource_suppressions(lambda_role,
                            suppressions=[{
                                            "id": "AwsSolutions-IAM5",
                                            "reason": "Lambda needs * access to all objects inside S3 bucket. And Bedrock all actions are allowed",
                                            }
                                        ],
                            apply_to_children=True)
        
        NagSuppressions.add_resource_suppressions(langchain_bedrock_lambda,
                            suppressions=[{
                                        "id": "AwsSolutions-L1",
                                        "reason": "Lets get this to work first before dealing with cfn_nag"
                                        }
                                    ]
                            )
