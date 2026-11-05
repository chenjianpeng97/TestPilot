@platform @dogfood
Feature: 测试工程师在 workspace 里的一天
  为了判断 workspace 骨架是否足以支撑日常测试工作
  作为一名测试工程师
  我希望知识回填、资产冻结、用例落地、工具开发与提交流程都能在仓内闭环

  @cli @needs-db @wip
  Scenario: 拉取表结构后沉淀一个造数动作词并试跑
    Given 已配置可连接的数据源 "main"
    When 我拉取表 "sample_table" 的表结构到知识层
    And 我按该表结构创建造数动作词 "db_seed.sample_seed"
    And 我用示例参数试跑该动作词
    Then 知识层应出现表 "sample_table" 的 DDL 文件
    And 动作词目录应包含 "db_seed.sample_seed"
    And 试跑结果应为成功

  @llm @needs-sut @wip
  Scenario: 探索被测系统的一个模块并冻结接口与页面资产
    Given 本机存在可用的探索账号
    When 我对一个垂直切片模块执行一轮探索式学习
    Then 证据目录应包含脱敏后的网络记录
    And 接口资产应按路由冻结
    And 页面资产应包含该模块的页面模型
    And 任务记录应列出探索过的页面与本轮新增资产

  @llm @needs-sut @wip
  Scenario: 从能力清单推导 Feature Set 并跑通回归产出报告
    Given 知识层已有该模块的能力清单与设计知识
    When 我推导 Feature Set 并实现对应步骤
    And 我运行该 Feature Set 所在 stage 的回归
    Then 回归报告应落在交付物目录
    And 报告清单应记录本次运行的状态与文件

  @cli @offline
  Scenario: 开发一个私有工具并在工作区目录中可见
    Given 工作区已有私有工具 "sample_tool"
    When 我查看该工具的用法说明
    And 我生成工作区目录
    Then 用法说明应列出参数 "--count" 与 "--label"
    And 工作区目录应包含工具 "sample_tool" 及其参数结构

  @cli @offline
  Scenario Outline: 按分层 scope 提交并得到确定性的校验结果
    Given 暂存了 "<path>" 的改动
    When 我用首行 "<header>" 提交
    Then 提交信息校验结果应为 "<result>"

    Examples:
      | path                       | header                                | result |
      | apps/sample_tool/cli.py    | feat(apps): add sample tool           | 通过   |
      | apps/sample_tool/cli.py    | feat(docs): add sample tool           | 拒绝   |
      | knowledge/ddl/main/t.sql   | chore(knowledge): refresh ddl         | 通过   |
      | knowledge/ddl/main/t.sql   | chore(assets): refresh ddl            | 拒绝   |
      | packages/action_words/a    | feat(packages): add seed word         | 通过   |
      | dogfood/README.md          | docs(dogfood): explain dogfood layout | 通过   |
