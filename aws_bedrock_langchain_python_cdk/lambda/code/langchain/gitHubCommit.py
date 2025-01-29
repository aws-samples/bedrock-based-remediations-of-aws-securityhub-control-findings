import logging
from github import Github, GithubException
import boto3

logging.basicConfig(level=logging.INFO)

class GitHubCommitter:
    def __init__(self, github_repo):
        # Retrieving GitHub access token from secrets manager 'github-token' secret.
        self.client = boto3.client('secretsmanager')
        try:
            self.oauth_token = self.client.get_secret_value(SecretId='github-token')['SecretString']
        except Exception as e:
            logging.error(f"Failed to retrieve GitHub token: {str(e)}")
            raise
        self.g = Github(self.oauth_token)
        self.repo = self.g.get_repo(github_repo)
        self.default_branch = self.repo.default_branch

    def read_file_content(self, filepath):
        with open(filepath, 'r') as file:
            return file.read()

    def create_file_path(self, resource_type, filename):
        return f'{resource_type}/GenRem-{filename}.yaml'

    def update_or_create_file(self, file_path, commit_message, file_content):
        try:
            # Try to get the file contents
            file = self.repo.get_contents(file_path, ref=self.default_branch)
            # If successful, update the existing file
            return self.repo.update_file(file_path, commit_message, file_content, file.sha, branch=self.default_branch)
        except GithubException as e:
            if e.status == 404:
                # If file not found, create a new file
                return self.repo.create_file(file_path, commit_message, file_content, branch=self.default_branch)
            else:
                # If it's a different kind of error, re-raise it
                raise

    def commit_file(self, filename, filepath, resource_type):
        file_content = self.read_file_content(filepath)
        file_path = self.create_file_path(resource_type, filename)
        commit_message = f"Push the remediation template for the security hub finding - {resource_type}"

        try:
            commit_response = self.update_or_create_file(file_path, commit_message, file_content)
            logging.info(f"File operation successful: {file_path}")
        except GithubException as e:
            logging.error(f"Error committing file: {e}")
            raise

        return commit_response, file_path