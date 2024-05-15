import logging
from remediation import RemediationHandler

# Logger 
LOGGER=logging.getLogger()
LOGGER.setLevel(logging.INFO)

# Setting baseline params
kb_id = 'RRBZ3ORVMO'
modelId = "anthropic.claude-3-sonnet-20240229-v1:0"
region = 'us-west-2'

prompt1 = """
        The following information is your only source of truth, only answer the question with the provided context, if you are unable to answer from that, tell the user Im having trouble finding an answer for you.
        
        You are an AWS security expert. You will be presented with a Security Hub finding Id or title. Your task is it to find if an Systems Manager automated document/runbook/playbook exists to remediate the finding.

        Approach this task step-by-step, take your time do not skip steps.
        
        1. Understand what is required to remediate the finding.
        2. Check if Security Hub can automate the remediation using a playbook from Automated Security Response on AWS
        2. Check if there is a runbook in the Systems Manager Automation runbook reference, which will automate the remediation for the finding.
        Provide the name of the AWS predefined playbook or runbook. 
        The name of the runbook will start with 'AWS', for example 'AWS-EnableS3BucketEncryption' or 'AWSConfigRemediation-EnableAPIGatewayTracing'
        The name of the ASR playbook will start with 'ASR', for example ' ASR-EnableLogFileValidation'
        Don't spread false information if a playbook or runbook does not exist.
        If you can't find a playbook or runbook, you will say 'no remediation available'. 
        
        Provide the following details: 
        
        * security_hub_finding_title
        * remediation_available (true or false)
        * remediation_runbook:
        * remediation_details:
        * resource_type

        Question: {question}
        Context: {context}
        {format_instructions}
        please output your response in the demanded json format
        """

prompt2 = """
        You will perform actions based on the inputs given to you
        Your task is to create a Cloudformation template to remediate the following security hub finding: {sechub_finding}.
        The template should be in YAML format.
        The template should automate the remediation process by SSM custom document
        Use the details provided to you help create the Cloudformation Template: {remediation_details}
        Don't exclude any resources for brevity.
        Ensure the code is syntactically correct based on AWS Cloudformation documentation and follows AWS Cloudformation best practices.
        If any resource is not added from the architecture diagram give the response on why it was not included. 

        Return only yaml code in Markdown format, e.g.:

        ```yaml
        ....
        ```
        """

prompt3 = """
        You are a security expert aimed to guide the customer how to remediate the following finding: {sechub_finding}
        You are aware that a remediation runbook is available for this finding. You will let the customer know that.
        Provide details on the runbook: {remediation_runbook}
        * First let the customer know that a remediation runbook is available for this finding.
        * Then provide details on the runbook.
        """

def rag_flow(sechub_finding, kb_id):
    remediation_handler = RemediationHandler(modelId, region)
    # Invoke the llm using retrieval QA
    response = remediation_handler.retrievalChain(prompt1, kb_id).invoke(
        "Is there a runbook to remediate the finding: {}?".format(sechub_finding)
    )
    LOGGER.info("Response_Chain_1: {}".format(response))
    # Store response details into params
    outputParams = {
        "remediation_runbook": response.remediation_runbook,
        "remediation_details": response.remediation_details,
        "resource_type": response.resource_type,
        "remediation_available": response.remediation_available,
        "resource_type": response.resource_type.replace(':','')
    }
    # Check if remediation_available is false. If it is, invoke the second chain to create the cloudformation template
    if not outputParams["remediation_available"]:
        response = remediation_handler.QAChain(prompt2).invoke(
            {"sechub_finding": sechub_finding, "remediation_details": outputParams["remediation_details"]}
        )
        LOGGER.info("Response_Chain_2: {}".format(response))
    else:
        # If remediation_available is true, invoke the third chain to provide the details on the runbook
        response = remediation_handler.QAChain(prompt3).invoke(
            {"sechub_finding": sechub_finding, "remediation_runbook": outputParams["remediation_runbook"]}
        )
        LOGGER.info("Response_Chain_3: {}".format(response))
    # return the response and the resource_type
    LOGGER.info("Final response: {}".format(response))
    return response, outputParams["resource_type"]

#Create a lambda function
def lambda_handler(event, context):
    LOGGER.info("Event: {}".format(event))
    remediation_handler = RemediationHandler(modelId, region)
    action = event["actionGroup"]
    api_path = event["apiPath"]
    if api_path == "/secHubRemediate/{sechub_finding}":
        sechub_finding = remediation_handler.get_named_parameter(event, "sechub_finding")
        rag_response, resource_type = rag_flow(sechub_finding, kb_id)
        LOGGER.info("RAG Response: {}".format(rag_response))
    # Check if rag_response contains a yaml code block. If it does, parse the yaml code and commit it to CodeCommit repo.
    if "```yaml" in rag_response:
        yaml_template = remediation_handler.parse_yaml_code(rag_response, sechub_finding.replace(" ", ""))
        commit_response, filepath = remediation_handler.commit_file(yaml_template, resource_type)
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
