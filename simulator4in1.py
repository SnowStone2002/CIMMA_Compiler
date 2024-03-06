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

# 计算input map到IS的mapping
# 对于Input_map 到 IS 的 mapping, 我们首先需要将一个channel的数据放入IS，如果一个channel放完，IS当前行未满，则后续补0，新的channel另起一行
input_data_per_row = m.floor(acc0.InputSRAMWidth / config.DATA_WIDTH)
rows_per_input_channel = m.ceil(input_map_length / input_data_per_row)
input_channels_per_ISload = m.floor(acc0.InputSRAMDepth / rows_per_input_channel)
IS_load_times_per_inst = m.ceil(input_map_channel / input_channels_per_ISload)

IS_load_rows = [input_channels_per_ISload * rows_per_input_channel] * (IS_load_times_per_inst)
if input_map_channel % input_channels_per_ISload != 0:
    IS_load_rows[IS_load_times_per_inst-1] = input_map_channel % input_channels_per_ISload * rows_per_input_channel

# 将weight map切成CIM size的block，放入CIM中
weight_block_row = m.ceil(weight_map_channel / config.PC)
weight_block_col = m.ceil(weight_map_length / config.AL)
weight_block_num = weight_block_col * weight_block_row
weight_update_times_per_inst = m.ceil(weight_block_num / config.SCR)

weight_update_ls = [config.SCR] * weight_update_times_per_inst
if weight_block_num % config.SCR != 0:
    weight_update_ls[weight_update_times_per_inst-1] = weight_block_num % config.SCR

para_times = weight_block_row
acc_times = weight_block_col

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

# OS & IS 反正没人看具体数据，无所谓，int8就行
IS = torch.zeros(acc0.InputSRAMDepth, acc0.InputSRAMWidth // config.DATA_WIDTH, dtype=torch.int8)
OS = torch.zeros(acc0.OutputSRAMDepth, acc0.OutputSRAMWidth // config.DATA_WIDTH // 4, dtype=torch.int32)

# CIMS 用bit存
CIMS = torch.zeros(acc0.CIMsrows, acc0.CIMsWriteWidth, dtype=torch.bool)

def LIS(reg = 0, IS_addr = 0, input_map_position = 0):
    i_input_map_channel = input_map_position // input_map_length
    i_input_data_channel = input_map_position % input_map_length
    byte_count = config.BUS_WIDTH // config.DATA_WIDTH
    IS[IS_addr, reg * byte_count: (reg+1) * byte_count] = input_map[i_input_map_channel, i_input_data_channel : i_input_data_channel + byte_count]

CIMaddress4 = [0, 0, 0, 0]

OS_output = torch.zeros(acc0.OutputSRAMWidth // config.DATA_WIDTH // 4, dtype=torch.int32)
def WU(reg = 0, CIMaddress = 0, weight_map_position = 0, ren = 0, read_addr = 0):
    global OS_output
    global CIMaddress4
    row_reg = (acc0.CIMsWriteWidth//acc0.BusWidth - 1 - reg) // (acc0.CIMsWriteWidth//acc0.BusWidth // config.WEIGHT_ROW)
    CIMaddress4[row_reg] = CIMaddress
    if row_reg == config.WEIGHT_ROW-1:
        byte_count = config.BUS_WIDTH // config.DATA_WIDTH
        i_weight_map_channel = weight_map_position // weight_map_length
        i_weight_data_channel = weight_map_position % weight_map_length
        datas = weight_map[i_weight_map_channel,i_weight_data_channel:i_weight_data_channel+4*byte_count]
        for i in range(byte_count*config.WEIGHT_ROW):
            for j in range(config.WEIGHT_ROW):
                CIMS[CIMaddress4[j],2*i] = datas[i]>>(2*j) & 1
                CIMS[CIMaddress4[j],2*i+1] = datas[i]>>(2*j+1) & 1
                # print(CIMS[CIMaddress4[j],2*i])
    if ren:
        OS_output = OS[read_addr,:]

sum_reg = torch.zeros(acc0.OutputSRAMWidth // config.DATA_WIDTH // 4, dtype=torch.int32)
psum = torch.zeros(acc0.OutputSRAMWidth // config.DATA_WIDTH // 4, dtype=torch.int32)
def CMPFIS(IS_addr = 0, CA = 0, atos = 0, OS_addr = 0, ren = 0, read_addr = 0):
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
    if atos == 0:
        sum_reg = psum + sum_reg
    elif atos == 1:
        OS[OS_addr,:] = sum_reg + psum
        sum_reg = torch.zeros(acc0.OutputSRAMWidth // config.DATA_WIDTH // 4, dtype=torch.int32)
    else:
        OS[OS_addr,:] = sum_reg + psum + OS_output
        sum_reg = torch.zeros(acc0.OutputSRAMWidth // config.DATA_WIDTH // 4, dtype=torch.int32)
    

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
            #print(parameters[0])
            if parameters[0] == "lis" | parameters[0] == "lisp":
                LIS(int(parameters[1]), int(parameters[2]), int(parameters[3]))

            elif parameters[0] == "wu" | parameters[0] == "wup":
                if len(parameters) > 4:
                    WU(int(parameters[1]), int(parameters[2]), int(parameters[3]), 1, int(parameters[5]))
                else:
                    WU(int(parameters[1]), int(parameters[2]), int(parameters[3]))

            elif parameters[0] == "cmpfis_int8":
                if parameters[3] == "aor":
                    atos = 0
                elif parameters[3] == "tos":
                    atos = 1
                else:
                    atos = 2
                if len(parameters) > 5:
                    CMPFIS(int(parameters[1]), int(parameters[2]), atos, int(parameters[4]), 1, int(parameters[6]))
                else:
                    CMPFIS(int(parameters[1]), int(parameters[2]), atos, int(parameters[4]))
        continue

print(OS)
print(golden_data)
