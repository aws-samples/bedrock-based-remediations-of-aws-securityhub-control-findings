import logging
import os
from remediation import RemediationHandler
from gitHubCommit import GitHubCommitter

# Logger 
LOGGER=logging.getLogger()
LOGGER.setLevel(logging.INFO)

kb_id = os.environ['KB_ID']
modelId = os.environ['MODEL_ID']
github_repo = os.environ['GITHUB_REPO']
github_owner = os.environ['GITHUB_OWNER']

prompt1 = """
        The following information is your only source of truth, only answer the question with the provided context, if you are unable to answer from that, tell the user Im having trouble finding an answer for you.

        You will be provided with the title of a security finding from AWS Security Hub. Your task is to
        determine if there is an automated remediation available for this finding, either through an AWS
        Security Hub Automated Security Response (ASR) playbook or an AWS Systems Manager Automation
        runbook.

        Approach this task step-by-step, take your time do not skip steps.
        Here are the steps to follow:

        1. Read the <security_hub_finding_title>{$security_hub_finding_title}</security_hub_finding_title>
        carefully and understand what is required to remediate this finding.

        2. Check if AWS Security Hub has an Automated Security Response (ASR) playbook to remediate this
        finding. ASR playbooks are pre-built automation workflows that can automatically remediate certain
        types of security findings.

        <scratchpad>
        Search the Automated Security Response (ASR) playbook related
        to the finding title. If an ASR playbook exists, note down its name which will start with "ASR", for
        example "ASR-EnableLogFileValidation".
        </scratchpad>

        3. If no ASR playbook is found, check if AWS Systems Manager has an Automation runbook to remediate
        this finding. Systems Manager runbooks are scripts that can automate common maintenance and
        deployment tasks.

        <scratchpad>
        Search the AWS Systems Manager Automation documentation for a runbook related to the
        finding title. If a runbook exists, note down its name which will start with "AWS", for example
        "AWS-EnableS3BucketEncryption" or "AWSConfigRemediation-EnableAPIGatewayTracing".
        </scratchpad>

        4. If either an ASR playbook or Systems Manager runbook is found, provide the following details:

        <remediation_available>true</remediation_available>

        <remediation_runbook>
        [Name of the ASR playbook or Systems Manager runbook]
        </remediation_runbook>

        <remediation_details>
        [Brief description of what the playbook/runbook does to remediate the finding]
        </remediation_details>

        5. If no ASR playbook or Systems Manager runbook is found to remediate the finding, provide the
        following:

        <remediation_available>false</remediation_available>
        <remediation_runbook>no remediation available</remediation_runbook>
        <remediation_details>
        [Brief description of how to manually remediate the finding]
        </remediation_details>

        6. Finally, identify the AWS resource type that the finding is related to and provide it in the
        following tag:

        <resource_type>
        [e.g. EC2 Instance, S3 Bucket, IAM Role, etc.]
        </resource_type>

        Make sure to follow the format exactly and do not include any additional information beyond what is
        requested. If you cannot find remediation details, simply state that no remediation is available.

        <context>
        {context}
        </context>

        <format_instructions>
        {format_instructions}
        </format_instructions>

        Only respond in the correct format, do not include additional properties in the JSON.
        """

prompt2 = """
        Your task is to create an AWS CloudFormation template in YAML format to remediate a Security Hub
        finding. The CloudFormation template will automate the remediation process using an AWS Systems
        Manager (SSM) custom document.

        CloudFormation is an AWS service that allows you to define and provision AWS resources in a
        declarative way using templates. A CloudFormation template is a JSON or YAML file that describes the
        desired state of your AWS resources.

        To create the CloudFormation template, you will need to use the following inputs:

        <sechub_finding>
        {sechub_finding}
        </sechub_finding>

        <remediation_details>
        {remediation_details}
        </remediation_details>

        Here are the steps to follow:

        1. Start by defining the required parameters in the CloudFormation template. These parameters will
        allow you to customize the resources during deployment. Based on the provided inputs, determine what
        parameters are needed (e.g., resource names, configurations, etc.).

        2. Define the required resources in the CloudFormation template based on the Security Hub finding
        and remediation details. This may include resources such as AWS Systems Manager documents, IAM
        roles, and any other resources needed for the remediation process.

        3. Create an AWS Systems Manager (SSM) custom document resource in the CloudFormation template. This
        document will contain the automation steps to remediate the Security Hub finding. Use the
        remediation details provided to define the steps in the SSM document.

        4. All automation scripts should be either in PowerShell or Python. Ensure scripts are in correct
        syntax and are valid AWS commands.

        5. Ensure that the CloudFormation template follows AWS best practices, such as separating resources
        into logical sections, using appropriate resource names, and adding descriptions for resources and
        parameters.

        6. Validate the CloudFormation template syntax and ensure it is compliant with the AWS
        CloudFormation documentation.

        7. If any resources are not included from the provided architecture diagram, explain why they were
        not included in the template.

        Once you have completed the CloudFormation template, provide the YAML code within Markdown code
        blocks, like this:

        ```yaml
        # Your CloudFormation template in YAML format
        ...
        ```

        Remember to follow AWS CloudFormation best practices and ensure that the provided YAML code is
        syntactically correct based on the AWS CloudFormation documentation.

        """

prompt3 = """
        You are a security expert guiding a customer on how to remediate the following finding:

        <finding>{sechub_finding}</finding>

        You are aware that a remediation runbook is available to address this finding. Here are the steps
        you should follow:
        
        <step1>
        First, let the customer know that a remediation runbook is available for the finding they received:

        "I want to inform you that a remediation runbook is available to help address the following finding:
        <finding>{sechub_finding}</finding>. This runbook provides step-by-step instructions on how to
        properly remediate this issue."
        </step1>

        <step2>
        Next, provide the details of the remediation runbook to the customer:

        <runbook_details>{remediation_runbook}</runbook_details>

        Encourage the customer to carefully follow the steps outlined in the runbook to ensure the finding
        is properly remediated.
        </step2>

        <step3>
        After providing the runbook details, ask the customer if they have any other questions or need
        further assistance regarding the remediation process. Be prepared to clarify any points or provide
        additional guidance as needed.
        </step3>

        Throughout the interaction, maintain a professional and helpful tone. The goal is to ensure the
        customer understands the finding, the importance of remediating it, and has clear instructions on
        how to do so via the provided runbook.

        """

def rag_flow(sechub_finding, kb_id):
    remediation_handler = RemediationHandler(modelId)
    
    # Invoke the llm using retrieval QA
    response = remediation_handler.retrievalChain(prompt1, kb_id).invoke(sechub_finding)
    LOGGER.info("Response_Chain_1: {}".format(response))
    # Store response details into params
    outputParams = {
        "remediation_runbook": response.remediation_runbook,
        "remediation_details": response.remediation_details,
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
    remediation_handler = RemediationHandler(modelId)
    action = event["actionGroup"]
    api_path = event["apiPath"]
    if api_path == "/secHubRemediate/{sechub_finding}":
        sechub_finding = remediation_handler.get_named_parameter(event, "sechub_finding")
        rag_response, resource_type = rag_flow(sechub_finding, kb_id)
        LOGGER.info("RAG Response: {}".format(rag_response))
    # Check if rag_response contains a yaml code block. If it does, parse the yaml code and commit it to CodeCommit repo.
    if "```yaml" in rag_response:
        yaml_template = remediation_handler.parse_yaml_code(rag_response)
        repo_name = github_owner + "/" + github_repo
        github_commiter = GitHubCommitter(repo_name)
        commit_response, filepath = github_commiter.commit_file(sechub_finding.replace(" ", ""), yaml_template, resource_type)
        # Return response with link to the commited file.
        rag_response = "The remediation runbook has been committed {} repo. File : {} with commit: {}".format(github_repo, filepath, commit_response['commit'].sha)

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
