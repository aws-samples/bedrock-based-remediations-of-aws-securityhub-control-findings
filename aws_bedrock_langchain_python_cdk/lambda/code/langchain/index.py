from langchain_community.retrievers import AmazonKnowledgeBasesRetriever
import boto3
from langchain.prompts import PromptTemplate
from botocore.client import Config
import logging
from langchain_community.chat_models import BedrockChat
from langchain_core.output_parsers import StrOutputParser, PydanticOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableParallel
from pydantic import BaseModel, Field, validator
import json
import warnings
import os

# Supress warnings
warnings.filterwarnings("ignore")

# Logger 
LOGGER=logging.getLogger()
LOGGER.setLevel(logging.INFO)

# boto3 configuration
s3_client = boto3.client("s3", region_name="us-west-2")
boto_config = Config(connect_timeout=900, read_timeout=900, retries={"max_attempts": 0})
bedrock_runtime = boto3.client(service_name="bedrock-runtime", config=boto_config, region_name="us-west-2")
bedrock_client = boto3.client(service_name="bedrock-agent-runtime", config=boto_config, region_name="us-west-2")

# parameters for codecommit grab from environment variables
# codecommit_repo_name = os.environ["codecommit_repo_name"]
# codecommit_branch_name = os.environ["codecommit_branch_name"]
codecommit_repo_name = "genai_remediations"
codecommit_branch_name = "main"



def get_llm():
    model_kwargs = {
    "max_tokens": 1024,
    "temperature": 1,
    "top_p": 0.99
}
    llm = BedrockChat(
        client = bedrock_runtime, #set the client for bedrock
        model_id="anthropic.claude-3-sonnet-20240229-v1:0", #set the foundation model
        model_kwargs=model_kwargs) #configure the properties for Claude
    return llm

def rag_for_sechubfindings(sechub_finding):
    retriever = AmazonKnowledgeBasesRetriever(
        knowledge_base_id="RRBZ3ORVMO",
        retrieval_config={"vectorSearchConfiguration": {"numberOfResults": 4}},
        client=bedrock_client,
        )
    llm = get_llm()

    ###############
    # First chain #
    ###############
    IAC_template = """
        Answer the question based only on the context given to you
        
        You are an AWS security expert. You are to find an automation runbook that will remediate the Security Hub finding.
        You will be provided with the following information: Security Hub finding.
        * Understand how this finding can be remediated, and search if remediation is available through a SSM runbook or ASR playbook
        * If available, provide the name of AWS Systems Manager predefined runbook or Automated Security Response Playbook. If automated remediation is not available through AWS, say there isn't one, dont try and make on up
        * Provide details on how to remediate the finding if runbook is not available.
        
        If you dont know the answer, dont try and make one up. Just say that you dont know the answer.
        
        Output the answer with the following details: 
        
        security_hub_finding_title:
        remediation_avaliable: (true or false)
        remediation_runbook:
        remediation_details:
        resource_type: 

        Question: {question}
        Context: {context}
        {format_instructions}
        """
    class sechub_output(BaseModel):
        remediation_details: str = Field(description="remediation_details")
        remediation_available: bool = Field(description="remediaiton_available")
        remediation_runbook: str = Field(description="remediation_runbook")
        security_hub_finding_title: str = Field(description="security_hub_finding_title")
        resource_type: str = Field(description="resource_type")

    parser=PydanticOutputParser(pydantic_object=sechub_output)

    iac_prompt_template= PromptTemplate(
        input_variables=["context", "question"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
        template=IAC_template,
    )

    setup_and_retrieval = RunnableParallel(
        {"context": retriever, "question": RunnablePassthrough()}
    )
    chain1 = ( setup_and_retrieval
        | iac_prompt_template
        | llm
        | parser
    )
    chain1_response = chain1.invoke("What is the remediation for the following security hub finding: {}".format(sechub_finding))
    remediation_details = chain1_response.remediation_details
    remediation_available = chain1_response.remediation_available
    remediation_runbook = chain1_response.remediation_runbook
    security_hub_finding_title = chain1_response.security_hub_finding_title
    resource_type = chain1_response.resource_type
    LOGGER.info(chain1_response)
    if not remediation_available:
        ################
        # Second chain #
        ################
        IAC_template2 = """
            You will perform actions based on the inputs given to you
            Your task is to create a Cloudformation template to remediate the following security hub finding: {sechub_finding}.
            The template should be in YAML format.
            The template should automate the remediation process by SSM custom document
            Use the details provided to you help create the Cloudformation Template: {remediation_details}
            Don"t exclude any resources for brevity.
            Ensure the code is syntactically correct based on AWS Cloudformation documentation and follows AWS Cloudformation best practices.
            If any resource is not added from the architecture diagram give the response on why it was not included. 

            Return only yaml code in Markdown format, e.g.:

            ```yaml
            ....
            ```
        """
        iac_prompt_template2 = PromptTemplate.from_template(IAC_template2)
        input = {"sechub_finding": sechub_finding, "remediation_details": remediation_details } 
        second_chain = (
            iac_prompt_template2
            | llm
            | StrOutputParser()
        )
        chain_response = second_chain.invoke(input)
    else: 
        ###########
        # Chain 3 #
        ###########
        IAC_template3 = """
            You are a security expert aimed to guide the customer how to remediate the following finding: {sechub_finding}
            You are aware that a remediation runbook is available for this finding. You will let the customer know that.
            Provide details on the runbook: {remediation_runbook}
            * First let the customer know that a remediation runbook is available for this finding.
            * Then provide details on the runbook.

        """
        iac_prompt_template3 = PromptTemplate.from_template(IAC_template3)
        input = {"sechub_finding": sechub_finding, "remediation_runbook": remediation_runbook}
        third_chain = (
            iac_prompt_template3
            | llm
            | StrOutputParser()
        )
        chain_response = third_chain.invoke(input)
    # Remove all ':' characters from resource_type
    resource_type = resource_type.replace(':', '')
    return chain_response, resource_type
    # return chain1_response

# Function to parse yaml code from string output. The yaml code will be in the block ```yaml ...```. Function should save the output to a yaml file in /tmp folder. The name of the file will be an input and should be prefixed "GenRem".
def parse_yaml_code(string_output, filename):
    filename = 'GenRem-{}.yaml'.format(filename)
    yaml_code = string_output.split("```yaml")[1].split("```")[0]
    with open("/tmp/{}".format(filename), "w") as f:
        f.write(yaml_code)
        f.close()
    #Return the filename
    return filename

# Create function to commit the yaml code into codecommit repository
def commit_file(filename, repo_name, branch_name, resource_type):
    codecommit_client = boto3.client("codecommit", region_name="us-west-2")
    with open("/tmp/{}".format(filename), "r") as f:
        file_content = f.read()
    #Get the latest commit id
    commit_id = codecommit_client.get_branch(repositoryName=repo_name, branchName=branch_name)["branch"]["commitId"]
    commit_response = codecommit_client.put_file(
        repositoryName=repo_name,
        branchName=branch_name,
        fileContent=file_content,
        filePath='{}/{}'.format(resource_type, filename),
        parentCommitId=commit_id,
        commitMessage="Committing the remediation runbook for the security hub finding",
    )
    return commit_response, '{}/{}'.format(resource_type, filename)

# Function to get parameter for bedrock
def get_named_parameter(event, name):
    return next(item for item in event["parameters"] if item["name"] == name)["value"]

#Create a lambda function
def lambda_handler(event, context):
    LOGGER.info("Event: {}".format(event))
    action = event["actionGroup"]
    api_path = event["apiPath"]
    if api_path == "/secHubRemediate/{sechub_finding}":
        sechub_finding = get_named_parameter(event, "sechub_finding")
        rag_response, resource_type = rag_for_sechubfindings(sechub_finding)
    # Check if rag_response contains a yaml code block. If it does, parse the yaml code and commit it to CodeCommit repo.
    if "```yaml" in rag_response:
        yaml_template = parse_yaml_code(rag_response, sechub_finding.replace(" ", ""))
        commit_response, filepath = commit_file(yaml_template, codecommit_repo_name, codecommit_branch_name, resource_type)
        # Return response with link to the commited file.
        rag_response = "The remediation runbook has been committed to CodeCommit repo. File : {} with commit ID: {}".format(filepath, commit_response['commitId'])

    response_body = {
        "application/json": {
            "body": rag_response
        }
    }
    action_response = {
        "actionGroup": event["actionGroup"],
        "apiPath": event["apiPath"],
        "httpMethod": event["httpMethod"],
        "httpStatusCode": 200,
        "responseBody": response_body
    }
    response = {"response": action_response}
    return response
