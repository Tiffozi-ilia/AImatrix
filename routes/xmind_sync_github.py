from github import Github
from github.InputGitAuthor import InputGitAuthor
from fastapi import APIRouter, Body
import requests
import os

router = APIRouter()

@router.post("/xmind-sync")
async def xmind_sync(url: str = Body(...)):

    g = Github('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')

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