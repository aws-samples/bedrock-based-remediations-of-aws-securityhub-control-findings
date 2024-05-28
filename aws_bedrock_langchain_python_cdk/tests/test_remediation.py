import boto3
from unittest.mock import patch, mock_open
import pytest
from aws_bedrock_langchain_python_cdk.lambda.code.langchain.remediation import RemediationHandler

@pytest.fixture
def mock_codecommit_client():
    with patch('boto3.client') as mock_boto3_client:
        mock_codecommit_client = mock_boto3_client.return_value
        mock_codecommit_client.get_branch.return_value = {'branch': {'commitId': 'abcdef01234'}}
        yield mock_codecommit_client

@pytest.fixture
def remediation_handler(monkeypatch, mock_codecommit_client):
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-east-1')
    remediation_handler = RemediationHandler()
    remediation_handler.codecommit_repo_name = 'my-repo'
    remediation_handler.codecommit_branch_name = 'main'
    return remediation_handler

def test_commit_file_with_commit_id(remediation_handler, mock_codecommit_client):
    file_path = 'my-resource/remediation.yaml'
    file_content = 'example: yaml\ncontent: here'

    with patch('builtins.open', mock_open(read_data=file_content)):
        commit_response, committed_file_path = remediation_handler.commit_file('remediation.yaml', 'my-resource')

    assert committed_file_path == file_path
    mock_codecommit_client.put_file.assert_called_with(
        repositoryName='my-repo',
        branchName='main',
        fileContent=file_content,
        filePath=file_path,
        parentCommitId='abcdef01234',
        commitMessage='Push the remediation template for the security hub finding'
    )

def test_commit_file_without_commit_id(remediation_handler, mock_codecommit_client):
    mock_codecommit_client.get_branch.side_effect = mock_codecommit_client.exceptions.BranchDoesNotExistException()
    file_path = 'my-resource/remediation.yaml'
    file_content = 'example: yaml\ncontent: here'

    with patch('builtins.open', mock_open(read_data=file_content)):
        commit_response, committed_file_path = remediation_handler.commit_file('remediation.yaml', 'my-resource')

    assert committed_file_path == file_path
    mock_codecommit_client.put_file.assert_called_with(
        repositoryName='my-repo',
        branchName='main',
        fileContent=file_content,
        filePath=file_path,
        commitMessage='Push the remediation template for the security hub finding'
    )
