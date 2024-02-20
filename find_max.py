import re

# 打开文件并读取内容
with open('./res.txt', 'r',encoding='utf-8') as file:
    content = file.read()

# 使用正则表达式找到所有 accuracy 值
acc_values = re.findall(r'acc: (\d+\.\d+)', content)

# 将字符串转换为浮点数，并找到最大值
acc_values = [float(acc) for acc in acc_values]
max_acc = max(acc_values)

print("最大的accuracy值为:", max_acc)
