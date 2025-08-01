from github import Github
from github.InputGitAuthor import InputGitAuthor
from fastapi import APIRouter
import codecs
import os

router = APIRouter()

@router.post("/xmind-sync")
async def xmind_sync(file):

    token = os.environ.get('GITHUB_TOKEN')
    g = Github(token)

    owner = 'Tiffozi-ilia'
    repo_name = 'AImatrix'
    file_path = 'matrix.xmind'
    branch = 'main'

    repo = g.get_repo(f"{owner}/{repo_name}")
    contents = repo.get_contents(file_path, ref=branch)

    with codecs.open(file, 'rb') as f:
        new_content = f.read()

    repo.update_file(
        contents.path,
        "Upload via DiFyBot",
        new_content,
        contents.sha,
        branch='main',
        author=InputGitAuthor("DiFyBot", "example@somemail.com"))