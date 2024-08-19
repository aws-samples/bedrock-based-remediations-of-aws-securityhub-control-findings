import os
import boto3
import logging
import warnings
from langchain_community.chat_models import BedrockChat
from langchain.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough, RunnableParallel
from langchain_core.output_parsers import StrOutputParser, PydanticOutputParser
from langchain_community.retrievers import AmazonKnowledgeBasesRetriever
from pydantic import BaseModel, Field


# Supress warnings
warnings.filterwarnings("ignore")

LOGGER = logging.getLogger(__name__)

class RemediationHandler:
    """
    This class encapsulates the functionality of identifying and handling remediation for Security Hub findings.
    It provides methods for retrieving LLM, analyzing findings, generating remediation instructions,
    and committing remediation code to a CodeCommit repository.
    """

    def __init__(self, modelId, region=os.environ['AWS_DEFAULT_REGION']):
        """
        Initialize the RemediationHandler instance with necessary AWS clients and configurations.
        """
        self.modelId = modelId
        self.s3_client = boto3.client("s3", region_name=region)
        boto_config = boto3.session.Config(connect_timeout=900, read_timeout=900, retries={"max_attempts": 0})
        self.bedrock_runtime = boto3.client(service_name="bedrock-runtime", config=boto_config, region_name=region)
        self.bedrock_client = boto3.client(service_name="bedrock-agent-runtime", config=boto_config, region_name=region)
        self.codecommit_repo_name = os.environ["codecommit_repo_name"]
        self.codecommit_branch_name = os.environ["codecommit_branch_name"]

    def get_llm(self):
        """
        Get the LLM (Large Language Model) instance used for generating remediation instructions.

        Returns:
            BedrockChat: An instance of the BedrockChat LLM with the specified configuration.
        """
        model_kwargs = {
            "max_tokens": 4096,
            "temperature": 0,
            "top_p": 0.99
        }
        llm = BedrockChat(
            client=self.bedrock_runtime,  # Set the client for Bedrock
            model_id=self.modelId,  # Set the foundation model
            model_kwargs=model_kwargs  # Configure the properties for Claude
        )
        return llm

    def retrievalChain(self, template, knowledge_id):
        """
        Create a retrieval chain for the given template, knowledge base ID, and parser.

        Args:
            template (str): The template to be used for the retrieval chain.
            knowledge_id (str): The knowledge base ID to be used for the retrieval chain.
            parser (PydanticOutputParser): The parser to be used for the retrieval chain.

        Returns:
            RetrievalChain: The retrieval chain for the given template, knowledge base ID, and parser.

        """
        retriever = AmazonKnowledgeBasesRetriever(
            knowledge_base_id=knowledge_id,
            retrieval_config={
                "vectorSearchConfiguration": {
                    "numberOfResults": 4,
                    "overrideSearchType": "HYBRID"
                }
            },
            client=self.bedrock_client,
        )
        llm = self.get_llm()
        parser = self.get_pydantic_parser()
        setup_and_retrieval = RunnableParallel(
            {"context": retriever, "$security_hub_finding_title": RunnablePassthrough()}
        )
        retrieval_chain = (
            setup_and_retrieval
            | PromptTemplate(
                input_variables=["context", "$security_hub_finding_title"],
                partial_variables={"format_instructions": parser.get_format_instructions()},
                template=template,
                )
            | llm
            | parser
        )
        return retrieval_chain

    def QAChain(self, template):
        """
        Create a QA chain for the given template
        Args:
            template (str): The template to be used for the QA chain.
        Returns:
            QAChain: The QA chain for the given template.
        """
        llm = self.get_llm()
        qa_chain = (
            PromptTemplate.from_template(template)
            | llm
            | StrOutputParser()
        )
        
        return qa_chain
    
    def get_pydantic_parser(self):
        """
        Create a parser for the output of the retrieval chain.

        Returns:
            PydanticOutputParser: The parser for the output of the retrieval chain.
        """
        class sechub_output(BaseModel):
            remediation_details: str = Field(description="remediation_details")
            remediation_available: bool = Field(description="remediation_available")
            remediation_runbook: str = Field(description="remediation_runbook")
            security_hub_finding_title: str = Field(description="security_hub_finding_title")
            resource_type: str = Field(description="resource_type")

        return PydanticOutputParser(pydantic_object=sechub_output)
    
    def parse_yaml_code(self, string_output, filename):
        """
        Parse the YAML code from the given string output and save it to a file.

        Args:
            string_output (str): The string containing the YAML code block.
            filename (str): The filename to be used for the generated YAML file.

        Returns:
            str: The filename of the generated YAML file.
        """
        filename = f'GenRem-{filename}.yaml'
        yaml_code = string_output.split("```yaml")[1].split("```")[0]
        with open(f"/tmp/{filename}", "w") as f:
            f.write(yaml_code)
        return filename

    def commit_file(self, filename, resource_type):
        """
        Commit the YAML file to the CodeCommit repository.

        Args:
            filename (str): The filename of the YAML file to be committed.
            resource_type (str): The resource type associated with the remediation.

        Returns:
            tuple: A tuple containing the commit response (dict) and the file path (str) in the repository.
        """
        codecommit_client = boto3.client("codecommit", region_name=os.environ['AWS_DEFAULT_REGION'])
        with open(f"/tmp/{filename}", "r") as f:
            file_content = f.read()
        # Get the latest commit ID
        commit_id = None
        try:
            commit_id = codecommit_client.get_branch(
                repositoryName=self.codecommit_repo_name,
                branchName=self.codecommit_branch_name
            )["branch"]["commitId"]
        except codecommit_client.exceptions.BranchDoesNotExistException:
            pass
        put_file_params = {
            'repositoryName': self.codecommit_repo_name,
            'branchName': self.codecommit_branch_name,
            'fileContent': file_content,
            'filePath': f'{resource_type}/{filename}',
            'commitMessage': "Push the remediation template for the security hub finding",
        }
        if commit_id:
            put_file_params['parentCommitId'] = commit_id
        commit_response = codecommit_client.put_file(**put_file_params)
        return commit_response, f'{resource_type}/{filename}'

    def get_named_parameter(self, event, name):
        """
        Get the value of a named parameter from the event dictionary.

        Args:
            event (dict): The event dictionary containing the parameters.
            name (str): The name of the parameter to retrieve.

        Returns:
            str: The value of the named parameter.
        """
        return next(item for item in event["parameters"] if item["name"] == name)["value"]
