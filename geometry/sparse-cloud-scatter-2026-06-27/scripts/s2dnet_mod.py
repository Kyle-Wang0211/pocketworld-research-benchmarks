# Standalone S2DNet (PixSfM 默认 featuremetric 稠密特征网) 重实现 + 加载官方权重。
# 绕开死掉的 pixsfm 包(其 __init__ 拉未构建的 _pixsfm C++)。num_layers=1 (conv1_2), D=128。
# 权重: dropbox hnv51iwu4hn82rj (s2dnet_weights.pth, 58MB)。
import torch, torch.nn as nn, torch.nn.functional as F
class S2DNet(nn.Module):
    def __init__(self, ckpt):
        super().__init__()
        # VGG-16 features[:4] = conv1_1, relu, conv1_2, relu -> 64ch stride-1
        self.enc=nn.Sequential(nn.Conv2d(3,64,3,padding=1),nn.ReLU(inplace=True),
                               nn.Conv2d(64,64,3,padding=1),nn.ReLU(inplace=True))
        # AdapLayer: Conv(64,64,1)->ReLU->Conv(64,128,5,pad2)->BN(128)
        self.adap=nn.Sequential(nn.Conv2d(64,64,1),nn.ReLU(),
                                nn.Conv2d(64,128,5,padding=2),nn.BatchNorm2d(128))
        sd=torch.load(ckpt,map_location='cpu',weights_only=False)
        if isinstance(sd,dict) and 'state_dict' in sd: sd=sd['state_dict']
        if isinstance(sd,dict) and 'model' in sd: sd=sd['model']
        self.enc[0].weight.data=sd['encoder.0.weight'];self.enc[0].bias.data=sd['encoder.0.bias']
        self.enc[2].weight.data=sd['encoder.2.weight'];self.enc[2].bias.data=sd['encoder.2.bias']
        a='adaptation_layers.adap_layer_0.'
        self.adap[0].weight.data=sd[a+'0.weight'];self.adap[0].bias.data=sd[a+'0.bias']
        self.adap[2].weight.data=sd[a+'2.weight'];self.adap[2].bias.data=sd[a+'2.bias']
        bn=self.adap[3];bn.weight.data=sd[a+'3.weight'];bn.bias.data=sd[a+'3.bias']
        bn.running_mean.data=sd[a+'3.running_mean'];bn.running_var.data=sd[a+'3.running_var']
        self.eval()
        self.register_buffer('mean',torch.tensor([0.485,0.456,0.406]).view(1,3,1,1))
        self.register_buffer('std',torch.tensor([0.229,0.224,0.225]).view(1,3,1,1))
    @torch.no_grad()
    def forward(self,x):  # x [B,3,H,W] in [0,1] -> [B,128,H,W] L2-normalized dense
        f=self.adap(self.enc((x-self.mean)/self.std))
        return F.normalize(f,dim=1)
