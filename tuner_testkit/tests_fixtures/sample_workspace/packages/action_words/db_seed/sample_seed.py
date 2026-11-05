"""示例造数动作词（仅 dry-run）。

工作台与「QA 一天」验收用的离线 fixture：演示 pydantic ``Params`` 如何变成表单、
破坏性动作如何要求确认。它**不会**连接任何数据库——``dry_run=False`` 时直接拒绝，
以免有人把示例当真实造数使用。真实 db_seed 请按 ``docs/spec/action-words-syntax.md``
声明 ``datasource`` 并经 ``self.db`` 落库。
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from packages.action_words import ActionCategory, ActionResult, ActionWord, register


@register
class SampleSeed(ActionWord):
    """示例造数：按数量生成样例订单行的 dry-run 计划。

    前置条件：无（离线）。副作用：无——本 word 只在 dry-run 模式下产出计划，
    真实落库被显式拒绝；因此 cleanup 恒为空。
    """

    word_id = "db_seed.sample_seed"
    name = "示例造数（dry-run）"
    category = ActionCategory.DB_SEED
    tags = ("dogfood", "示例")
    requires = frozenset()
    example_params = {"count": 2, "prefix": "DEMO", "dry_run": True}

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")

        count: int = Field(1, ge=1, le=50, description="要生成的样例行数")
        prefix: str = Field("SAMPLE", min_length=1, description="样例单号前缀")
        dry_run: bool = Field(True, description="只生成计划不落库（示例 word 仅支持 True）")

    class Result(ActionResult):
        planned_nos: list[str] = Field(default_factory=list, description="计划生成的样例单号")

    def run(self, params: "SampleSeed.Params") -> "SampleSeed.Result":
        if not params.dry_run:
            raise AssertionError("db_seed.sample_seed 是离线示例，只支持 dry_run=True")
        planned = [f"{params.prefix}-{index:03d}" for index in range(1, params.count + 1)]
        return self.Result(
            ok=True,
            detail={"mode": "dry-run", "rows": len(planned)},
            planned_nos=planned,
        )


if __name__ == "__main__":
    # 手工改参入口：python -m packages.action_words.db_seed.sample_seed
    from tuner_testkit.action_words import ActionContext

    with ActionContext() as ctx:
        print(SampleSeed(ctx).run_from_dict({"count": 3, "prefix": "MANUAL", "dry_run": True}).model_dump())
