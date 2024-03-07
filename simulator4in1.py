from hw_config import hwc
from hw_config import Config
import math as m
import torch

# 可变参数
config = Config(al=128, pc=16, scr=4, bus_width=128, is_depth=512, os_depth=1024)
acc0 = hwc(config)
gli = ['mvm', (80, 512, 64)]
data_stream = 'wspp'
file_path = 'mi.log'

# 两个length对应作点乘，channel互相无关
weight_map_channel = gli[1][0]
weight_map_length = gli[1][1]

input_map_length  = gli[1][1]
input_map_channel  = gli[1][2]

original_weight_map = torch.randint(-128, 128, size=(weight_map_channel, weight_map_length), dtype=torch.int8)
original_input_map = torch.randint(-128, 128, size=(input_map_channel, input_map_length), dtype=torch.int8)

# 将原始矩阵转换为int32类型
weight_map_int32 = original_weight_map.to(dtype=torch.int32)
input_map_int32 = original_input_map.to(dtype=torch.int32)

# # 执行矩阵乘法，并保证结果为int32类型
golden_data = input_map_int32 @ weight_map_int32.transpose(0, 1)

para_times = weight_map_channel // config.PC
acc_times = weight_map_length // config.AL

# 计算AL和PC整数倍的扩展矩阵尺寸
operating_weight_map_channel = para_times * config.PC
operating_weight_map_length = acc_times * config.AL

operating_input_map_length  = acc_times * config.AL
operating_input_map_channel  = input_map_channel

# 先创建长宽均为AL和PC整数倍的全0矩阵
weight_map = torch.zeros((operating_weight_map_channel, operating_weight_map_length), dtype=torch.int8)
input_map = torch.zeros((operating_input_map_channel, operating_input_map_length), dtype=torch.int8)

# 复制原始矩阵到扩展矩阵的相应位置
weight_map[:weight_map_channel, :weight_map_length] = original_weight_map
input_map[:input_map_channel, :input_map_length] = original_input_map

# OS & IS 用int8存
IS = torch.zeros(acc0.InputSRAMDepth, acc0.InputSRAMWidth // config.DATA_WIDTH, dtype=torch.int8)
OS = torch.zeros(acc0.OutputSRAMDepth, acc0.OutputSRAMWidth // config.DATA_WIDTH // 4, dtype=torch.int32)

# CIMS 用bit存
CIMS = torch.zeros(acc0.CIMsrows, acc0.CIMsWriteWidth, dtype=torch.bool)

CIMaddress4 = [0, 0, 0, 0] #用4是为了区分，实际上4是weight row

OS_output = torch.zeros(acc0.OutputSRAMWidth // config.DATA_WIDTH // 4, dtype=torch.int32)

sum_reg = torch.zeros(acc0.OutputSRAMWidth // config.DATA_WIDTH // 4, dtype=torch.int32)
psum = torch.zeros(acc0.OutputSRAMWidth // config.DATA_WIDTH // 4, dtype=torch.int32)

wu_row_reg = 0
data_reg = torch.zeros(acc0.CIMsComputeWidth // config.DATA_WIDTH, dtype=torch.int8)

def LIS(reg = 0, IS_addr = 0, in_map_pos = 0):
    global IS
    i_input_map_channel = in_map_pos // input_map_length
    i_input_data_channel = in_map_pos % input_map_length
    byte_count = config.BUS_WIDTH // config.DATA_WIDTH
    IS[IS_addr, reg * byte_count: (reg+1) * byte_count] = input_map[i_input_map_channel, i_input_data_channel : i_input_data_channel + byte_count]

def WU(reg = 0, CIMaddress = 0, wt_map_pos = 0, ren = 0, read_addr = 0):
    global OS_output
    global CIMaddress4
    global wu_row_reg
    # row_reg = (acc0.CIMsWriteWidth//acc0.BusWidth - 1 - reg) // (acc0.CIMsWriteWidth//acc0.BusWidth // config.WEIGHT_ROW)
    wu_reg = wu_row_reg * config.WEIGHT_COL + reg
    byte_count = acc0.CIMsWriteWidth // config.WEIGHT_COL

    CIMaddress4[wu_row_reg] = CIMaddress

    i_weight_map_channel = wt_map_pos // weight_map_length
    i_weight_data_channel = wt_map_pos % weight_map_length

    data_reg[wu_reg*config.BUS_WIDTH//config.DATA_WIDTH:(wu_reg+1)*config.BUS_WIDTH//config.DATA_WIDTH] = weight_map[i_weight_map_channel,i_weight_data_channel:i_weight_data_channel+config.BUS_WIDTH//config.DATA_WIDTH]
    
    if (wu_row_reg == config.WEIGHT_ROW-1) and (reg == config.WEIGHT_COL-1):
        for i in range(byte_count):
            for j in range(config.WEIGHT_ROW):
                CIMS[CIMaddress4[j],2*i] = data_reg[i]>>(2*j) & 1
                CIMS[CIMaddress4[j],2*i+1] = data_reg[i]>>(2*j+1) & 1
        wu_row_reg = 0
    elif reg == config.WEIGHT_COL-1:
        wu_row_reg += 1

    if ren:
        OS_output = OS[read_addr,:]

def CMPFIS(IS_addr = 0, CA = 0, atos = 'aor', OS_addr = 0, ren = 0, read_addr = 0):
    global sum_reg
    global OS_output
    global psum
    activation = IS[IS_addr,:]
    psum = torch.zeros(acc0.OutputSRAMWidth // config.DATA_WIDTH // 4, dtype=torch.int32)
    for i in range(config.PC):
        for j in range(config.AL):
            for k in range(config.WEIGHT_ROW):
                row = i * config.WEIGHT_ROW * config.SCR + k * config.SCR + CA
                if k != config.WEIGHT_ROW-1:
                    psum[i] += (CIMS[row,2*j].to(dtype=torch.int32) * pow(2,2*k) + CIMS[row,2*j+1].to(dtype=torch.int32) * pow(2,2*k+1)) * activation[j].to(dtype=torch.int32)
                else:
                    psum[i] += (CIMS[row,2*j].to(dtype=torch.int32) * pow(2,2*k) - CIMS[row,2*j+1].to(dtype=torch.int32) * pow(2,2*k+1)) * activation[j].to(dtype=torch.int32)
    if ren:
        OS_output = OS[read_addr,:]
    if atos == 'aor':
        sum_reg = psum + sum_reg
    elif atos == 'tos' or atos == 'ptos':
        OS[OS_addr,:] = sum_reg + psum
        sum_reg = torch.zeros(acc0.OutputSRAMWidth // config.DATA_WIDTH // 4, dtype=torch.int32)
    else:
        OS[OS_addr,:] = sum_reg + psum + OS_output
        sum_reg = torch.zeros(acc0.OutputSRAMWidth // config.DATA_WIDTH // 4, dtype=torch.int32)

def Load_OS_Output(read_addr = 0):
    global OS_output
    OS_output = OS[read_addr,:]

count = 0
with open(file_path, 'r') as file:
    start_processing = False
    for line in file:

        count+=1
        print(count)

        # 检查是否到达 "starting compiler:"
        if 'starting compiler:' in line:
            start_processing = True
            print("start processing")
            continue
        
        # 如果已经开始处理
        if start_processing:
            # get the instruction
            parameters = line.split()

            if parameters[0] == "lis" or parameters[0] == "lis_p":
                LIS(reg         =   int(parameters[2]), 
                    IS_addr     =   int(parameters[4]), 
                    in_map_pos  =   int(parameters[6]))

            elif parameters[0] == "wu" or parameters[0] == "wu_p":
                if "<os_addr_rd>" in parameters:
                    WU(reg         =   int(parameters[2]), 
                       CIMaddress  =   int(parameters[4]), 
                       wt_map_pos  =   int(parameters[6]), 
                       ren         =   1, 
                       read_addr   =   int(parameters[8]))
                else:
                    WU(reg         =   int(parameters[2]), 
                       CIMaddress  =   int(parameters[4]), 
                       wt_map_pos  =   int(parameters[6]), 
                       ren         =   0, 
                       read_addr   =   0)

            elif parameters[0] == "cmpfis":
                if "<os_addr_rd>" in parameters:
                    CMPFIS(IS_addr      =   int(parameters[2]), 
                           CA           =   int(parameters[4]), 
                           atos         =   parameters[5], 
                           OS_addr      =   int(parameters[7]), 
                           ren          =   1, 
                           read_addr    =   int(parameters[9]))
                else:
                    CMPFIS(IS_addr      =   int(parameters[2]), 
                           CA           =   int(parameters[4]), 
                           atos         =   parameters[5], 
                           OS_addr      =   int(parameters[7]), 
                           ren          =   0, 
                           read_addr    =   0)

            elif parameters[0] == "nop":
                if "<os_addr_rd>" in parameters:
                    Load_OS_Output(read_addr = parameters[2])

            elif parameters[0] == "pload":
                if "<os_addr_rd>" in parameters:
                    Load_OS_Output(read_addr = parameters[2])
        continue

print(OS)
print(golden_data)
