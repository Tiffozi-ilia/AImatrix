import xml.etree.ElementTree as ET
import pandas as pd
import io

# Примерный DataFrame, заменяется на build_df_from_api() в реальной версии
df = pd.DataFrame([
    {"id": "a.a.01", "title": "Главная", "body": "Описание", "parent_id": "", "level": "1"},
    {"id": "a.a.01.01", "title": "Дочерняя", "body": "Описание 2", "parent_id": "a.a.01", "level": "2"},
])

# Создание элементов карты
def build_mm_structure(df):
    nodes = {row["id"]: ET.Element("node", {
        "TEXT": row["title"],
        "ID": row["id"],
        "level": row["level"]
    }) for _, row in df.iterrows()}

    root_node = None
    for _, row in df.iterrows():
        node = nodes[row["id"]]
        if row["parent_id"]:
            parent = nodes.get(row["parent_id"])
            if parent is not None:
                parent.append(node)
        else:
            root_node = node

    map_elem = ET.Element("map", version="1.0.1")
    if root_node is not None:
        map_elem.append(root_node)
    return ET.ElementTree(map_elem)

tree = build_mm_structure(df)

# Сериализация для проверки
buf = io.BytesIO()
tree.write(buf, encoding="utf-8", xml_declaration=True)
buf.seek(0)
buf.getvalue().decode("utf-8")[:1000]
