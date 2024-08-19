## AWS Bedrock Langchain Python CDK for Security Hub Automated Remediations

This repository contains an AWS Cloud Development Kit (CDK) application written in Python, which deploys an AWS Lambda function and the necessary infrastructure to support automated remediations for AWS Security Hub standard findings using a large language model powered by Langchain.

### Solution Overview

This solution follows prescriptive guidance for automating remediations for AWS Security Hub standard findings.

1. The SecOps user utilizes the Agents for Amazon Bedrock chat console to enter their responses (e.g. "Generate automation for remediation of database migration service replication instances should not be public"). Optionally, findings can be exported from Security Hub to an Amazon S3 bucket.

2. The request invokes a large language model (LLM) with context from a knowledge base containing AWS documentation stored as embeddings in an Amazon OpenSearch vector database.

3. The LLM generates instructions for an action group that invokes the Remediation Generator AWS Lambda function to create a Systems Manager automation document.

4. The automation document is published to an AWS CodeCommit repository.

5. The SecOps user updates parameter files for the automation in a document management system folder, triggering AWS CodePipeline.

6. AWS CodeBuild runs cfn-lint and cfn-nag validations on the CloudFormation template.

7. An Amazon SNS notification is sent to the SecOps user group for approval before deployment.

8. The approved Systems Manager automation document is executed.

9. The SecOps user validates the compliance status for the remediated finding in the Security Hub console.

### Deployment

Follow these steps to deploy the CDK application:

1. **Configure the Amazon Bedrock agent**
   - Open the Amazon Bedrock console, select Agents in the left navigation panel, then choose Create Agent.
   - Provide agent details including agent name and description (optional).
   - Next, grant the agent permissions to AWS services through AWS Identity and Access Management (IAM) service role. This gives your agent access to required services, such as AWS Lambda.
   - Select a foundation model (FM) from Amazon Bedrock (such as Anthropic Claude V2).
   - To automate remediation of Security Hub findings using Amazon Bedrock agents, attach the following instruction to the agent:
     "You are an AWS security expert, tasked to help customer remediate security related findings.
     Inform the customer what your objective is. Gather relevant information such as finding Id or finding title so that you can perform your task.
     * With information given you will attempt to find an automated remediation of the finding and provide to the customer as IaC."

2. **Configure a knowledge base**
   - Access the Amazon Bedrock console. Sign in and go directly to the Knowledge Base section.
   - Name your knowledge base. Choose a clear and descriptive name that reflects the purpose of your knowledge base, such as "AWSAutomationRunbooksPlaybooks."
   - Select an IAM role. Assign a preconfigured IAM role with the necessary permissions. It's typically best to let Amazon Bedrock create this role for you to ensure it has the correct permissions.
   - Define the data source. For this solution, we are using three AWS documentation guides in PDF that covers all AWS provided automations through runbooks or playbooks. Upload the PDF files from the `data-source` folder in the Git repo to an S3 bucket. 
   - Choose the default embeddings model. The Amazon Titan Embeddings G1 is a text model that is preconfigured and ready to use, simplifying the process.
   - Opt for the managed vector store. Allow Amazon Bedrock to create and manage the vector store for you in Amazon OpenSearch Service.
   - Review and finalize. Double-check all entered information for accuracy. Pay special attention to the S3 bucket URI and IAM role details.
   - After successful creation, copy the knowledge base ID because you will need to reference it in the next step.

3. **Deploy the CDK project**
   - First, download the CDK project repository containing the solution's infrastructure code. You can find the repository at the following location: [GitHub Repo Link] (placeholder).
   - Bootstrap CDK. Before deploying the solution, you need to bootstrap your AWS environment for CDK. Run the following command to bootstrap your environment: `cdk bootstrap aws://<your-aws-account-id>/<your-aws-region>`
   - Configure CDK App. Navigate to the downloaded CDK project directory and open the `app.py` file.
     - Update the following parameters in the file:
       - `aws_region`: Set the AWS Region where you want to deploy the solution.
       - `bedrock_knowledge_base_id`: Provide the ID of the Amazon Bedrock knowledge base you set up manually in the prerequisites.
       - `codecommit_branch`: Specify the branch of the CodeCommit repository you want to use.
   - Synthesize CDK app. Run the following command to synthesize the CDK app and generate the CloudFormation template: `cdk synth`
   - Deploy CDK app. Finally, deploy the solution to your AWS environment using the following command: `cdk deploy --all`. This command will deploy all the necessary resources, including the Remediation Generator Lambda function, the CodeCommit repository, the CodePipeline, and other required components.

1. Ensure AWS CDK is installed and configured.
2. Clone this repository.
3. Navigate to the root directory.
4. Run `cdk deploy` to deploy the stack.

### File Details

The `app.py` file is the main entry point for the CDK application. It defines the CDK stack and its resources, such as Lambda functions, CodeCommit repositories, CodePipelines, and more.

1. **Imports**: The file starts by importing the necessary modules and classes from the AWS CDK and other libraries.

2. **Stack Definition**: The `AwsBedRockLangchainPythonCdkStack` class extends the `Stack` class from the AWS CDK. It contains the definitions for all the resources that will be deployed.

3. **Parameters**: The `AwsBedRockLangchainPythonCdkStack` class constructor accepts several parameters, such as the AWS region, the Amazon Bedrock knowledge base ID, and the CodeCommit repository branch.

4. **Resource Definitions**:
   - **CodeCommit Repository**: A CodeCommit repository is created to store the Systems Manager automation documents.
   - **Remediation Generator Lambda Function**: A Lambda function is created to generate the Systems Manager automation documents based on the input from the Amazon Bedrock agent.
   - **Other Resources**: Depending on the specific requirements, additional resources like S3 buckets, SNS topics, and IAM roles may be defined.

5. **Resource Dependencies**: The stack defines dependencies between resources to ensure the correct order of deployment.

6. **Outputs**: The stack may define outputs to display relevant information after deployment, such as the CodeCommit repository URL or the Remediation Generator Lambda function ARN.

The `index.py` file contains the code for the Remediation Generator Lambda function. This function is responsible for generating the Systems Manager automation documents based on the input from the Amazon Bedrock agent.

1. **Imports**: The file starts by importing the necessary modules and libraries.

2. **Lambda Handler**: The `lambda_handler` function is the entry point for the Lambda function. It receives the event and context objects as input.

3. **Input Processing**: The function processes the input received from the Amazon Bedrock agent, which may include information about the security finding and the desired remediation action.

4. **Document Generation**: Based on the input, the function generates the Systems Manager automation document. This may involve parsing the input, retrieving relevant information from the knowledge base, and constructing the document using predefined templates or logic.

5. **Document Storage**: Once the automation document is generated, the function stores it in the CodeCommit repository specified in the stack.

6. **Output**: The function may return a response indicating the successful generation and storage of the automation document.

### Other Files

Depending on the specific implementation, there may be additional files or directories in the `aws_bedrock_langchain_python_cdk` folder. These files may contain utility functions, configurations, or other supporting code for the CDK application and the Remediation Generator Lambda function.

