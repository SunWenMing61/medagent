"""
${message}

Revision ID: ${up_revision}           {# 迁移版本的唯一标识符，由 Alembic 自动生成 #}
Revises: ${down_revision | comma,n}  {# 前置迁移版本号（可能多个），用于回滚时定位 #}
Create Date: ${create_date}           {# 迁移脚本的创建时间戳 #}

"""  {# 模块文档字符串，描述该迁移的内容、依赖关系和创建时间 #}
from typing import Sequence, Union

from alembic import op            {# alembic 操作模块，提供 alter/create/drop 等 DDL 操作函数 #}
import sqlalchemy as sa           {# SQLAlchemy 核心库，用于定义列类型和约束 #}
${imports if imports else ""}     {# 自动导入额外的模块（如新增的自定义类型），可能为空 #}

# revision identifiers, used by Alembic.
# Alembic 使用的版本标识变量，用于跟踪迁移链
revision: str = ${repr(up_revision)}                               {# 当前迁移版本号（字符串） #}
down_revision: Union[str, None] = ${repr(down_revision)}           {# 前置迁移版本号，None 表示这是第一个迁移 #}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}  {# 分支标签，用于多分支迁移场景 #}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}  {# 依赖的其他迁移（即使不在同一分支链上） #}


def upgrade() -> None:
    """
    升级函数：定义如何将数据库从上一版本升级到当前版本。

    在此函数中编写 DDL 操作（CREATE TABLE、ALTER TABLE、ADD COLUMN 等）。
    所有操作应设计为可重复执行（幂等）或仅在首次执行时生效。
    """
    ${upgrades if upgrades else "pass"}  {# 升级操作内容，未定义时使用 pass（空操作） #}


def downgrade() -> None:
    """
    降级函数：定义如何将数据库从当前版本回滚到上一版本。

    通常与 upgrade() 的操作相反（如 CREATE 对应 DROP，ADD COLUMN 对应 DROP COLUMN）。
    必须能干净地回退到上一版本状态。
    """
    ${downgrades if downgrades else "pass"}  {# 降级操作内容，未定义时使用 pass（空操作） #}
