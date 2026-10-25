# 目标加载yml中的数据，供创建主和子智能体使用
import yaml # yaml配置文件读取
from pathlib import Path

# 定义一个加载函数，配置文件yaml加载成字典
def load_yaml(file_path):
    """
    加载指定位置的yaml配置文件
    :param file_path:  加载的文件的地址
    :return:  返回的加载结果 本质就是字典
    """
    with open(file_path, 'r', encoding='utf-8') as f :
        # safe_load 只会加载，不会触发！
        # load 加载过程中可能无意执行内部的嵌入函数！！ 可能发生注入脚本攻击
        # 用 yaml.safe_load 读文件，得到 dict（注释里说明比 load 更安全）
        # 把文件对象f里面的YAML文本读取并解析,转换成Python字典
        return yaml.safe_load(f)

# 尝试读取主和子智能体的配置文件和数据（供后续使用）
# 项目的根地址
# project_root_path  = Path(__file__).parent.parent
project_root_path  = Path(__file__).parents[1] # prompts -> parents -> [agent , deep_search_pro]
yaml_file_path = project_root_path / "prompt" / "prompts.yml"

#调用函数读上面地址的文件
prompt_yaml_content = load_yaml(yaml_file_path)


# main_agent_content
main_agent_content = prompt_yaml_content["main_agent"]

# import agent.prompts（或间接 import main_agent），启动时会在控制台打出整段 Prompt，调试可以，生产一般会删掉。
#print(main_agent_content)

# sub_agents_content
sub_agents_content = prompt_yaml_content["sub_agents"]

#print(sub_agents_content)

#看yaml.safe_load将yaml转换成什么类型
#print(type(prompt_yaml_content))