from github import Github
from github.InputGitAuthor import InputGitAuthor
from fastapi import APIRouter
import requests
import os

router = APIRouter()

@router.post("/xmind-sync")
async def xmind_sync(url):

    token = os.environ.get('GITHUB_TOKEN')
    g = Github(token)

    owner = 'Tiffozi-ilia'
    repo_name = 'AImatrix'
    file_path = 'matrix.xmind'
    branch = 'all-in'

    repo = g.get_repo(f"{owner}/{repo_name}")
    contents = repo.get_contents(file_path, ref=branch)

    response = requests.get(url)
    new_content = response.content

    # with codecs.open(file, 'rb') as f:
    #     new_content = f.read()

    repo.update_file(
        contents.path,
        "Upload via DiFyBot",
        new_content,
        contents.sha,
        branch=branch,
        author=InputGitAuthor("DiFyBot", "example@somemail.com"))