#!/usr/bin/env python
# coding: utf-8

# ### 导入相关的包

# In[2]:


from torch.utils.data import Dataset, DataLoader
import torch
import torch.nn as nn
import numpy as np
from torch.optim.lr_scheduler import LambdaLR,ReduceLROnPlateau
from torchvision import datasets
from sklearn.neighbors import NearestNeighbors
from sklearn.model_selection import train_test_split
import torch.nn.functional as F
from torch.nn import TripletMarginLoss
import torch.nn.init as init
from torch.utils.tensorboard import SummaryWriter
import pandas as pd
from torchvision import transforms
from PIL import Image
import os
import random

def start_train():
    print('Start Training')
    print('-'*10)
    # 用mx来记录最大的acc值
    mx=0
    for epoch in range(epochs):
        # print('\n循环 {}/{}'.format(epoch + 1, epochs))
        # print('-' * 10)
        with open('./res.txt','a+',encoding='utf-8') as f:
            f.write(f'\n循环 {epoch + 1}/{epochs}\n')
            f.write('------------------------------------------------------------------------------------\n' )
        
        model.train()
        # 代价损失计算并且保存在结果文件中
        cost_loss=0
        # 用来计算被划分了多少个批次
        cnt=0
        running_loss = 0.0
        for i, data in enumerate(train_loader, 0):
            anchor, positive, negative = data[0]
            anchor, positive, negative = anchor.to('cuda'), positive.to('cuda'), negative.to('cuda')
            optimizer.zero_grad()
            anchor_out = model(anchor)
            positive_out = model(positive)
            negative_out = model(negative)
            loss_val = loss(anchor_out, positive_out, negative_out)
            loss_val.backward()
            optimizer.step()
            running_loss += loss_val.item()
            # writer.iteration += 1
            # print(f"the loss is {running_loss}")
            cost_loss+=running_loss
            cnt+=1
            # 不知道干嘛的
            # if i % 10 == 9:
            #     # writer.add_scalar('loss', running_loss / 10,
            #     #                   writer.iteration)
            #     running_loss = 0.0
        # print('Epoch{} finished'.format(epoch))
        with open('./res.txt','a+',encoding='utf-8') as f:
            f.write(f'The cost_loss is {cost_loss/cnt/batch_size} \n Epoch{epoch} finished\n')
        
        
        model.eval()
        ## we use acc to evaluate the model
        with torch.no_grad():
            # 用标签来评估模型
            total = 0
            correct = 0
            reference_embeddings_np = np.vstack([embedding.cpu().numpy() for embedding in reference_embeddings])
            near_nn = NearestNeighbors(n_neighbors=1, algorithm='auto',metric='euclidean',).fit(reference_embeddings_np)
            # use labels to evaluate the model
            for i,data in enumerate(test_loader,0):
                    anchor_validation, _, _ = data[0]
                    anchor_label, _, _ = data[1]
                    batch_sizes = anchor_validation.size(0)
                    total += batch_sizes
                    anchor_validation = anchor_validation.to('cuda')
                    # print(anchor.shape)
                    anchor_out_validation = model(anchor_validation).cpu().detach().numpy()
                    # print('anchor_out_validation:', anchor_out_validation)
                    distances, indices = near_nn.kneighbors(anchor_out_validation)
                    indices = indices.reshape(-1)
                    
                    for j in range(batch_sizes):
                        if reference_labels[indices[j]] == anchor_label[j]:
                            correct += 1
            acc = correct / total
            # print('acc:', acc)
            # print('correct:', correct)
            if mx < acc:
                mx=acc
            with open('./res.txt','a+',encoding='utf-8') as f:
                f.write(f'acc: {acc}\n')
                f.write(f'correct: {correct}\n')
            # writer.add_scalar('acc', acc, epoch)
            
            # 用scheduler来更新学习率
            scheduler.step(acc)
            # current_lr = scheduler.get_last_lr()
            # print("Current learning rate: ", current_lr)

            #全都扔进去
            # print('lr:', optimizer.param_groups[0]['lr'])
            with open('./res.txt','a+',encoding='utf-8') as f:
                f.write('lr: {}\n'.format(optimizer.param_groups[0]['lr']))
            
    print('Finished Training')
    with open('./res.txt','a+',encoding='utf-8') as f:
        f.write('finish training\n')
        f.write(f'the max acc is {acc}')

# ### 部署模型，修改分类层

# In[3]:


# 使用预训练参数
from models.SqueezeNet import SqueezeNet

model = SqueezeNet(version="1_1")
model.load_state_dict(torch.load('squeezenet1_1_weights.pth'))


# 冻结参数层
for param in model.parameters():
    param.requires_grad = False

# 修改最后一层

# 不打印了
# print(model.classifier[1])
final_conv = nn.Conv2d(512, 128, kernel_size=1)
init.normal_(final_conv.weight, mean=0.0, std=0.01)
init.constant_(final_conv.bias, 0.0)
model.classifier[1] = final_conv


model = model.to('cuda')



for params in model.classifier[1].parameters():
    params.requires_grad = True
    
# 解冻模型的最后1个Fire模块
for param in model.features[-1:].parameters():
    param.requires_grad = True
    
    
print(model)


# In[4]:

transforming = transforms.Compose([
    transforms.Resize((224, 224)),
    # 数据增强
    transforms.RandomHorizontalFlip(),  # 随机水平翻转，有助于人脸识别任务
    transforms.RandomRotation(10),  # 随机旋转，-10到10度之间
    transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),  # 随机调整亮度、对比度和饱和度
    transforms.RandomAffine(degrees=0, translate=(0.1, 0.1), scale=(0.9, 1.1), shear=10),  # 随机仿射变换
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[
                                 0.229, 0.224, 0.225])
        ])



# ### 读取并且定制数据集

# In[5]:


loss = TripletMarginLoss(margin=0.2, p=2)


# 分割三元组数据集
class TripletFaceDataset(Dataset):
    def __init__(self, image_folder,persons,transform=None):
        self.image_folder = image_folder
        self.transform = transform
        self.persons = persons

    def __getitem__(self, _):
        anchor_person = random.choice(self.persons)
        positive_person = anchor_person
        negative_person = random.choice(self.persons)
        while negative_person == anchor_person:
            negative_person = random.choice(self.persons)

        anchor_img_path = random.choice(os.listdir(
            os.path.join(self.image_folder, anchor_person)))
        positive_img_path = random.choice(os.listdir(
            os.path.join(self.image_folder, positive_person)))
        negative_img_path = random.choice(os.listdir(
            os.path.join(self.image_folder, negative_person)))

        anchor_img = Image.open(os.path.join(
            self.image_folder, anchor_person, anchor_img_path))
        positive_img = Image.open(os.path.join(
            self.image_folder, positive_person, positive_img_path))
        negative_img = Image.open(os.path.join(
            self.image_folder, negative_person, negative_img_path))

        # 进行数据处理
        transform = self.transform

        anchor_img = transform(anchor_img)
        positive_img = transform(positive_img)
        negative_img = transform(negative_img)

        return (anchor_img, positive_img, negative_img),(anchor_person, positive_person, negative_person)

    def __len__(self):
        return len(self.persons) * 5  # 假设每个人有5张图片


# print(labels)

# 切割数据集八二分

batch_size = 64
epochs = 50
workers = 0 if os.name == 'nt' else 8


dataset = datasets.ImageFolder('./data_cropped', transform=transforming)
labels = os.listdir('./data_cropped')

random.shuffle(labels)
train_idx, test_idx = train_test_split(
    labels, test_size=0.2, random_state=42)

train_dataset = TripletFaceDataset(
    image_folder='./data_cropped', persons=train_idx, transform=transforming
    )

test_dataset = TripletFaceDataset(
    image_folder='./data_cropped', persons=test_idx, transform=transforming
    )

train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=workers)
test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False, num_workers=workers)




# In[6]:

#模型训练前准备
# 定制优化器
# 0.00001
optimizer = torch.optim.Adam(model.parameters(), lr=0.0000001)

# def lambda_rule(epoch,max_epoch):
#     max_epoch = 20
#     return (1-epoch/max_epoch)**0.9 ##多项式衰减

# scheduler = LambdaLR(optimizer, lr_lambda=lambda_rule)

#每两轮进行一次学习率的更新，寻找最优的学习率
scheduler = ReduceLROnPlateau(optimizer, mode='max', factor=0.5, patience=5)

# 定制参考嵌入向量
reference_embeddings = []
reference_labels = []
model.eval()
# 遍历数据集每个文件夹，每个文件夹embeddings计算平均值，放进reference_embeddings,对应的标签放进reference_labels
for label in labels:
    label_embeddings = []
    for img_path in os.listdir(os.path.join('./data_cropped', label)):
        img = Image.open(os.path.join('./data_cropped', label, img_path))
        img = transforming(img).to('cuda')
        img = img.unsqueeze(0)
        with torch.no_grad():
            embedding = model(img).cpu().detach().numpy()
            label_embeddings.append(embedding)    
    label_embeddings = np.array(label_embeddings)
    np_mean = np.mean(label_embeddings, axis=0)
    tensor_mean = torch.from_numpy(np_mean).to('cuda')
    reference_embeddings.append(tensor_mean)
    reference_labels.append(label)


# print(reference_embeddings)
# print(reference_labels)


# ### 开始训练

start_train()

# In[ ]:


# writer = SummaryWriter('runs/triplet_loss_experiment')
# writer.iteration, writer.interval = 0, 10



# writer.close()

        
                    
                    
                
              
            
            
            

