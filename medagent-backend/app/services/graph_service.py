"""
GraphRAG（图检索增强生成）服务。

提供基于内存知识图谱的实体提取、图搜索和混合检索（图+向量）功能。
轻量级实现，无需 Neo4j 等外部图数据库依赖。
"""

# 从 __future__ 导入 annotations，启用注解的延迟求值（PEP 604）
from __future__ import annotations

# 导入标准库类型和工具
from typing import List, Optional, Dict, Set, Tuple, Any
from collections import deque
import json
import logging

# 导入配置，获取 LLM 相关设置
from app.core.config import settings

logger = logging.getLogger(__name__)


# ==================== 内存知识图谱 ====================


class GraphStore:
    """轻量级内存知识图谱，使用 Python dict/set 实现。

    支持实体和关系的增删查改，以及基于 BFS（广度优先搜索）的子图查询。
    所有操作幂等且不会抛出异常（异常时返回空结果）。
    """

    def __init__(self):
        # 实体存储：entity_id -> {type, name, metadata}
        self._entities: Dict[str, dict] = {}
        # 邻接表：entity_id -> [(relation_type, target_id, metadata)]
        self._adjacency: Dict[str, List[Tuple[str, str, dict]]] = {}
        # 反向邻接表：entity_id -> [(relation_type, source_id, metadata)]
        self._reverse_adjacency: Dict[str, List[Tuple[str, str, dict]]] = {}

    def add_entity(self, entity_id: str, entity_type: str, name: str,
                   metadata: Optional[dict] = None) -> None:
        """添加或更新一个实体。

        Args:
            entity_id: 实体唯一标识符
            entity_type: 实体类型（disease / drug / symptom / treatment / exam）
            name: 实体名称
            metadata: 可选的附加元数据字典
        """
        try:
            self._entities[entity_id] = {
                "type": entity_type,
                "name": name,
                "metadata": metadata or {},
            }
            # 确保邻接表中存在该实体的条目
            if entity_id not in self._adjacency:
                self._adjacency[entity_id] = []
            if entity_id not in self._reverse_adjacency:
                self._reverse_adjacency[entity_id] = []
        except Exception:
            logger.exception("添加实体失败: entity_id=%s", entity_id)

    def add_relation(self, source_id: str, target_id: str, relation_type: str,
                     metadata: Optional[dict] = None) -> None:
        """添加或更新两个实体之间的关系。

        Args:
            source_id: 源实体 ID
            target_id: 目标实体 ID
            relation_type: 关系类型（treats / causes / side_effect / indicates / contraindicates）
            metadata: 可选的附加元数据字典
        """
        try:
            meta = metadata or {}
            # 正向边
            edge = (relation_type, target_id, meta)
            # 避免重复添加相同的边
            if source_id in self._adjacency:
                existing = [(r, t) for r, t, _ in self._adjacency[source_id]]
                if (relation_type, target_id) not in existing:
                    self._adjacency[source_id].append(edge)
            # 反向边
            reverse_edge = (relation_type, source_id, meta)
            if target_id in self._reverse_adjacency:
                existing_rev = [(r, s) for r, s, _ in self._reverse_adjacency[target_id]]
                if (relation_type, source_id) not in existing_rev:
                    self._reverse_adjacency[target_id].append(reverse_edge)
        except Exception:
            logger.exception("添加关系失败: %s ->[%s]-> %s", source_id, relation_type, target_id)

    def get_entity(self, entity_id: str) -> Optional[dict]:
        """根据 ID 获取实体信息。

        Returns:
            实体字典 {type, name, metadata}，如不存在返回 None
        """
        try:
            return self._entities.get(entity_id)
        except Exception:
            logger.exception("获取实体失败: entity_id=%s", entity_id)
            return None

    def get_entity_by_name(self, name: str) -> Optional[Tuple[str, dict]]:
        """根据名称查找实体（不区分大小写）。

        Returns:
            (entity_id, entity_dict) 元组，未找到返回 None
        """
        try:
            name_lower = name.lower().strip()
            for eid, ent in self._entities.items():
                if ent["name"].lower().strip() == name_lower:
                    return eid, ent
            return None
        except Exception:
            logger.exception("按名称查找实体失败: name=%s", name)
            return None

    def search(self, query_entities: List[str], max_depth: int = 2) -> List[dict]:
        """从指定实体出发，BFS 遍历图，返回关联的子图。

        Args:
            query_entities: 起始实体 ID 列表
            max_depth: BFS 遍历的最大深度，默认 2

        Returns:
            子图结果列表，每条记录的格式为：
            {entity: dict, relation: str, connected_entity: dict, depth: int}
        """
        results: List[dict] = []
        try:
            # 如果查询列表为空，直接返回空结果
            if not query_entities:
                return results

            # BFS 初始化：队列中存储 (entity_id, depth)
            queue: deque = deque()
            visited: Set[str] = set()
            for qe in query_entities:
                if qe in self._entities:
                    queue.append((qe, 0))
                    visited.add(qe)

            while queue:
                current_id, depth = queue.popleft()
                # 超过最大深度不再继续扩展
                if depth >= max_depth:
                    continue

                current_entity = self._entities.get(current_id, {})
                neighbor_depth = depth + 1

                # 遍历正向邻接边
                for rel_type, neighbor_id, rel_meta in self._adjacency.get(current_id, []):
                    neighbor_entity = self._entities.get(neighbor_id, {})
                    results.append({
                        "entity": current_entity,
                        "relation": rel_type,
                        "relation_metadata": rel_meta,
                        "connected_entity": neighbor_entity,
                        "direction": "outgoing",
                        "depth": neighbor_depth,
                    })
                    if neighbor_id not in visited and neighbor_entity:
                        visited.add(neighbor_id)
                        queue.append((neighbor_id, neighbor_depth))

                # 遍历反向邻接边（指向当前节点的边）
                for rel_type, source_id, rel_meta in self._reverse_adjacency.get(current_id, []):
                    source_entity = self._entities.get(source_id, {})
                    results.append({
                        "entity": source_entity,
                        "relation": rel_type,
                        "relation_metadata": rel_meta,
                        "connected_entity": current_entity,
                        "direction": "incoming",
                        "depth": neighbor_depth,
                    })
                    if source_id not in visited and source_entity:
                        visited.add(source_id)
                        queue.append((source_id, neighbor_depth))

        except Exception:
            logger.exception("图搜索失败: query_entities=%s", query_entities)
        return results

    def get_all_entities(self) -> Dict[str, dict]:
        """获取所有实体的只读视图。"""
        return dict(self._entities)

    def get_context_text(self, query_entities: List[str], max_depth: int = 2) -> str:
        """以可读文本格式输出查询相关的子图上下文。

        Args:
            query_entities: 起始实体 ID 列表
            max_depth: BFS 遍历的最大深度

        Returns:
            格式化后的子图描述文本，适合作为 LLM 上下文
        """
        try:
            subgraph = self.search(query_entities, max_depth)
            if not subgraph:
                return ""

            lines: List[str] = ["【相关医学知识图谱】"]
            seen_relations: Set[str] = set()

            for item in subgraph:
                entity_name = item["entity"].get("name", "未知")
                entity_type = item["entity"].get("type", "未知")
                rel_type = item["relation"]
                conn_name = item["connected_entity"].get("name", "未知")
                conn_type = item["connected_entity"].get("type", "未知")

                # 去重描述
                relation_key = f"{entity_name}|{rel_type}|{conn_name}"
                if relation_key in seen_relations:
                    continue
                seen_relations.add(relation_key)

                # 关系类型的友好中文描述
                rel_desc = _relation_type_to_chinese(rel_type)
                lines.append(
                    f"- [{entity_type}] {entity_name} --[{rel_desc}]--> "
                    f"[{conn_type}] {conn_name}"
                )

            if len(lines) > 1:
                return "\n".join(lines)
            return ""
        except Exception:
            logger.exception("生成图上下文文本失败")
            return ""


def _relation_type_to_chinese(rel_type: str) -> str:
    """将关系类型枚举转换为友好的中文描述。"""
    mapping = {
        "treats": "治疗",
        "causes": "引发",
        "side_effect": "副作用",
        "indicates": "提示",
        "contraindicates": "禁忌",
        "diagnosed_by": "诊断依据",
        "associated_with": "关联",
        "prevents": "预防",
        "manages": "管理",
    }
    return mapping.get(rel_type, rel_type)


# ==================== 全局单例 ====================

# 全局内存图谱实例，应用生命周期内共享
_graph_store = GraphStore()


# ==================== 实体提取 ====================


# 实体提取的 Prompt 模板
_ENTITY_EXTRACTION_PROMPT = """你是一个专业的医疗实体提取助手。请从以下文本中提取所有医疗相关的命名实体。

实体类型包括：
- disease（疾病/病症）
- drug（药物/药品）
- symptom（症状/体征）
- treatment（治疗方案/手术/疗法）
- exam（检查/检验/影像学检查）

请以 JSON 数组格式返回，每个元素包含 type（实体类型）和 name（实体名称）字段，以及可选的 attributes（属性字典）。
只返回 JSON 数组，不要返回其他内容。

文本内容：
{text}
"""


def extract_entities(text: str) -> List[dict]:
    """使用 LLM 从文本中提取医疗实体。

    调用配置的大语言模型进行命名实体识别（NER），
    返回规范化的实体列表。

    Args:
        text: 需要提取实体的输入文本

    Returns:
        实体字典列表，格式为 {type, name, attributes?}
        提取失败或文本为空时返回空列表
    """
    if not text or not text.strip():
        return []

    try:
        # 检查 LLM 配置是否就绪
        api_key = settings.LLM_API_KEY
        if not api_key:
            logger.warning("LLM_API_KEY 未配置，跳过实体提取")
            return []

        # 构建请求 payload
        prompt = _ENTITY_EXTRACTION_PROMPT.format(text=text[:4000])  # 截断过长的文本

        import httpx
        response = httpx.post(
            f"{settings.LLM_API_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": settings.LLM_MODEL,
                "messages": [
                    {"role": "system", "content": "你是一个医疗实体提取助手，只输出 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,  # 低温度确保结果稳定
                "max_tokens": 2000,
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()

        # 尝试从返回中解析 JSON
        # 处理模型可能返回 markdown 代码块的情况
        if content.startswith("```"):
            # 提取代码块中的 JSON 内容
            content = content.split("\n", 1)[-1]
            content = content.rsplit("```", 1)[0]
            content = content.strip()

        entities = json.loads(content)
        if isinstance(entities, list):
            # 标准化：确保每个实体都有 type 和 name 字段
            normalized = []
            for ent in entities:
                if isinstance(ent, dict) and "type" in ent and "name" in ent:
                    normalized.append({
                        "type": str(ent["type"]).lower(),
                        "name": str(ent["name"]).strip(),
                        "attributes": ent.get("attributes", {}),
                    })
            logger.info("实体提取完成：共提取 %d 个实体", len(normalized))
            return normalized
        return []
    except json.JSONDecodeError:
        logger.warning("实体提取结果 JSON 解析失败: content=%s", content[:200])
        return []
    except Exception:
        logger.exception("实体提取调用失败")
        return []


# ==================== 图上下文获取 ====================


def get_graph_context(query: str, entities: List[str]) -> str:
    """根据查询文本和实体列表，获取格式化的子图上下文。

    在内存图谱中查找与指定实体关联的邻居节点，
    生成适合注入 LLM 的文本描述。

    Args:
        query: 原始查询文本（当前主要用于日志追踪）
        entities: 实体 ID 或名称列表

    Returns:
        格式化后的子图描述文本，未找到相关图信息时返回空字符串
    """
    try:
        # 优先按 ID 查找；如果找不到，尝试按名称模糊匹配
        resolved_ids: List[str] = []
        for ent in entities:
            if ent in _graph_store._entities:
                resolved_ids.append(ent)
            else:
                # 按名称查找
                found = _graph_store.get_entity_by_name(ent)
                if found:
                    resolved_ids.append(found[0])
                else:
                    # 将实体名称作为新的临时节点尝试搜索
                    resolved_ids.append(ent)

        return _graph_store.get_context_text(resolved_ids, max_depth=2)
    except Exception:
        logger.exception("获取图上下文失败: query=%s", query[:100])
        return ""


# ==================== 混合搜索（图 + 向量） ====================


# ==================== 对外暴露的快捷函数 ====================


def add_entity(entity_id: str, entity_type: str, name: str,
               metadata: Optional[dict] = None) -> None:
    """向全局内存图谱添加实体（快捷函数）。"""
    _graph_store.add_entity(entity_id, entity_type, name, metadata)


def add_relation(source_id: str, target_id: str, relation_type: str,
                 metadata: Optional[dict] = None) -> None:
    """向全局内存图谱添加关系（快捷函数）。"""
    _graph_store.add_relation(source_id, target_id, relation_type, metadata)


def search_graph(query_entities: List[str], max_depth: int = 2) -> List[dict]:
    """在全局内存图谱中执行搜索（快捷函数）。"""
    return _graph_store.search(query_entities, max_depth)


def get_store() -> GraphStore:
    """获取全局 GraphStore 实例。"""
    return _graph_store
