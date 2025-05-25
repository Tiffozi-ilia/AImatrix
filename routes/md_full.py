from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from utils.data_loader import build_df_from_api
import yaml
import pandas as pd

router = APIRouter()

@router.get("/md/full")
def export_md_full():
    df = build_df_from_api()

    def format_linked(row):
        linked = []

        if pd.notna(row.get("parent_id")):
            linked.append({"type": "parent", "id": row["parent_id"]})

        child_ids = row.get("child_id")
        if isinstance(child_ids, list):
            for cid in child_ids:
                linked.append({"type": "child", "id": cid})
        elif pd.notna(child_ids):
            if isinstance(child_ids, str) and "," in child_ids:
                for cid in child_ids.split(","):
                    linked.append({"type": "child", "id": cid.strip()})
            else:
                linked.append({"type": "child", "id": child_ids})

        return linked

    blocks = []
    for _, row in df.iterrows():
        meta_block = {
            "id": row["id"],
            "title": row["title"]
        }

        if pd.notna(row.get("parent_id")):
            meta_block["parent_id"] = row["parent_id"]

        if pd.notna(row.get("parent_name")):
            meta_block["parent_name"] = row["parent_name"]

        linked = format_linked(row)
        if linked:
            meta_block["linked"] = linked

        yaml_meta = yaml.dump(meta_block, allow_unicode=True, sort_keys=False)
        indented_yaml = "\n".join("  " + line for line in yaml_meta.splitlines())

        block = (
            f"# {row['title']}\n\n"
            f"<!-- METADATA -->\n"
            f"meta:\n{indented_yaml}\n"
            f"<!-- END -->\n\n"
            f"{row['body']}\n\n---"
        )
        blocks.append(block)

    content = "\n\n".join(blocks)
    return PlainTextResponse(content, media_type="text/markdown")
