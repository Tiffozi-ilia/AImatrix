from github import Github
from github.InputGitAuthor import InputGitAuthor
from fastapi import APIRouter, Body
import requests
import os
import json

router = APIRouter()

@router.post("/xmind-sync")
async def xmind_sync(url: dict = Body(...)):

    url = url['url']
    
    logs = []

    def log(msg):
        print(msg)
        logs.append(msg)

    log(f'[XMIND-SYNC] got url dify')
    log(url)

    GIT_TOKEN = os.environ.get('GITHUB_TOKEN')

    g = Github(GIT_TOKEN)

    owner = 'Tiffozi-ilia'
    repo_name = 'AImatrix'
    file_path = 'matrix.xmind'
    branch = 'all-in'

    repo = g.get_repo(f"{owner}/{repo_name}")
    contents = repo.get_contents(file_path, ref=branch)

    response = requests.get(url)
    new_content = response.content

    log(f'[XMIND-SYNC] got new content')

    repo.update_file(
        contents.path,
        "Upload via DiFyBot",
        new_content,
        contents.sha,
        branch=branch,
        author=InputGitAuthor("DiFyBot", "example@somemail.com"))
    
    log(f'[XMIND-SYNC] xmind updated')