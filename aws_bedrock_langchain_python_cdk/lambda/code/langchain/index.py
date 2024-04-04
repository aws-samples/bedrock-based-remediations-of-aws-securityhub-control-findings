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
codecommit_repo_name = os.environ["codecommit_repo_name"]
codecommit_branch_name = os.environ["codecommit_branch_name"]



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
        
        You are an AWS security expert. You are to provide an automation runbook to remediate the Security Hub finding.
        You will be provided with the following information: Security Hub finding.
        * Understand how this finding can be remediated, if the remediation is available through a runbook or playbook 
        * Provide the AWS Systems Manager predefined runbook or Automated Security Response Playbook if available. If automated remediation is not available for the finding, say there isn't one, dont try and make on up
        * Provide details on how to remediate the finding.
        
        If you dont know the answer, dont try and make one up. Just say that you dont know the answer.
        
        Output the answer in json in the following format: 
        
        security_hub_finding_title:
        remediation_avaliable: (true or false)
        remediation_runbook:
        remediation_details:

        Question: {question}
        Context: {context}
        
        """
    iac_prompt_template= PromptTemplate(
        input_variables=["context", "question"],
        # partial_variables={"format_instructions": parser.get_format_instructions()},
        template=IAC_template,
    )

    setup_and_retrieval = RunnableParallel(
        {"context": retriever, "question": RunnablePassthrough()}
    )
    chain1 = ( setup_and_retrieval
        | iac_prompt_template
        | llm
        | StrOutputParser()
    )
    chain1_response = chain1.invoke("What is the remediation for the following security hub finding: {}".format(sechub_finding))
    # remediation_available = chain1_response["remediation_avaliable"]
    # remediation_runbook = chain1_response["remediation_runbook"]
    # remediation_details = chain1_response["remediation_details"]
    # sechub_finding = chain1_response["sechub_finding_title"]
    
    if  'remediation_available: "false"' or 'remediation_available: false' in chain1_response:
        ################
        # Second chain #
        ################
        IAC_template2 = """
            You will perform actions based on the inputs given to you
            Create a Cloudformation template to remediate the following security hub finding: {sechub_finding}.
            The template should be in YAML format.
            Don"t exclude any resources for brevity.
            The Cloudformation template should be in YAML format.
            Define outputs for critical resources.
            Ensure the code is syntactically correct based on AWS Cloudformation documentation and follows AWS Cloudformation best practices.
            If any resource is not added from the architecture diagram give the response on why it was not included. 

            Return only yaml code in Markdown format, e.g.:

            ```yaml
            ....
            ```
        """
        iac_prompt_template2 = PromptTemplate.from_template(IAC_template2)
        input = {"sechub_finding": sechub_finding }
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
        input = {"sechub_finding": sechub_finding}
        third_chain = (
            iac_prompt_template3
            | llm
            | StrOutputParser()
        )
        chain_response = third_chain.invoke(input) 
    return chain_response

# Function to parse yaml code from string output. The yaml code will be in the block ```yaml ...```. Function should save the output to a yaml file. The name of the file will be an input and should be prefixed "GenRem".
def parse_yaml_code(string_output, filename):
    yaml_code = string_output.split("```yaml")[1].split("```")[0]
    file = 'GenRem-{}'.format(filename)
    with open(file, "w") as f:
        f.write(yaml_code)
    return yaml_code

# Function to commit the file to CodeCommit repo
def commit_file(file, repo_name, branch_name):
    codecommit_client = boto3.client("codecommit")
    response = codecommit_client.put_file(
        repositoryName=repo_name,
        branchName=branch_name,
        fileContent=file,
        filePath=file,
    )
    return response

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
        rag_response = rag_for_sechubfindings(sechub_finding)
    # Check if rag_response contains a yaml code block. If it does, parse the yaml code and commit it to CodeCommit repo.
    if "```yaml" in rag_response:
        yaml_code = parse_yaml_code(rag_response, sechub_finding.replace(" ", ""))
        commit_response = commit_file(yaml_code, codecommit_repo_name, codecommit_branch_name)
        # Return response with link to the commited file.
        rag_response = "The remediation runbook has been committed to CodeCommit repo. The link to the commited file is: {}".format(commit_response["commitId"])

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
