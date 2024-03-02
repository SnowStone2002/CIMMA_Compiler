# Micro Instruction Compiler
# Input: hardware config, graph level instruction
# Output: micro instructions

# datatype: INT8
# CIM is bit parallel

# Mode - WSAP

from hw_config import hwc
from hw_config import Config
import write_history 
from append_read import add_read_n_lines_before
import math as m
import torch

# 可变参数
config = Config(al=128, pc=2, scr=2, is_depth=4, os_depth=1024)

acc0 = hwc(config)

gli = ['mvm', (2, 512, 2)]

# 两个length对应作点乘，channel互相无关
weight_map_channel = gli[1][0]
weight_map_length = gli[1][1]

input_map_length  = gli[1][1]
input_map_channel  = gli[1][2]

# 计算input map到IS的mapping
# region 载入尽量多的input vector, min{lac*scr, lat},只存一次
input_data_per_row = m.floor(acc0.InputSRAMWidth / config.DATA_WIDTH)
rows_per_input_channel = m.ceil(input_map_length / input_data_per_row)
input_channels_per_ISload = min(acc0.InputSRAMDepth // rows_per_input_channel, input_map_channel)
# endregion

# region 将weight map切成CIM size的block，放入CIM中
weight_block_row = m.ceil(weight_map_channel / config.PC)
weight_block_col = m.ceil(weight_map_length / config.AL)
weight_block_num = weight_block_col * weight_block_row
weight_update_times_per_inst = m.ceil(weight_block_num / config.SCR)

weight_update_ls = [config.SCR] * weight_update_times_per_inst
if weight_block_num % config.SCR != 0:
    weight_update_ls[weight_update_times_per_inst-1] = weight_block_num % config.SCR
# endregion

para_times = weight_block_row
acc_times = weight_block_col

# region 下面两个矩阵非常重要，ls代表了每一次cim计算local switch的状态（用第几个存储的数据做计算）
ls_matrix = torch.zeros(para_times,acc_times) # local switch
ls_fg = 0
for i_pt in range(para_times):
    for i_at in range(acc_times):
        ls_matrix[i_pt,i_at] = ls_fg
        ls_fg = ls_fg+1
        if ls_fg == config.SCR: ls_fg = 0

# atos matrix 代表了这一次计算的外部数据流方向
    # 0:aor reg = reg + psum
    # 1:tos OS = reg + psum, reg = 0
    # 2:aos OS = psum + reg + OS, reg = 0
aor, tos, aos = 0, 1, 2
atos_dict = ['aor','tos','aos']

atos_matrix = torch.zeros(para_times,acc_times)
for i_pt in range(para_times):
    row_st_fg = 0 # row start flag
    for i_at in range(acc_times):    
        # 0:aor, 1:tos, 2:aos
        if i_at == acc_times-1 or ls_matrix[i_pt,i_at] == acc0.LocalSwitchrows - 1:
            if row_st_fg == 0: 
                atos_matrix[i_pt,i_at] = tos
                row_st_fg = 1
            else:
                atos_matrix[i_pt,i_at] = aos
# endregion
                
def LOG_INIT():
    with open('wsap.log','w') as f:
        f.write("starting compiler:\n")

def IDLE():
    with open('wsap.log','a') as f:
        f.write("nop\n")

def LOADIS_BLOCK(num_rows, input_map_position): #输入现在正要存的数据在input map中的位置，以及需要输入多少行
    with open('wsap.log','a') as f:
        for i_rows in range(num_rows):
            # input_map_position = (i_rows // rows_per_input_channel) * input_map_length # channel 对应的
            # + (i_rows % rows_per_input_channel) * acc0.InputSRAMWidth // config.DATA_WIDTH # row 对应的
            # + int(config.BUS_WIDTH / config.DATA_WIDTH) * (acc0.InputSRAMWidth//acc0.BusWidth - 1) #一行内用于递减的position reg
            input_map_position += int(config.BUS_WIDTH / config.DATA_WIDTH) * (acc0.InputSRAMWidth//acc0.BusWidth - 1)
            for j_reg in reversed(range(acc0.InputSRAMWidth//acc0.BusWidth)):
                if j_reg != 0:
                    f.write("lisp\t"+str(j_reg)+"\t"+str(i_rows)+"\t"+str(input_map_position)+"\n")
                else:
                    f.write("lis\t\t"+str(j_reg)+"\t"+str(i_rows)+"\t"+str(input_map_position)+"\n")
                input_map_position -= int(config.BUS_WIDTH / config.DATA_WIDTH)
            input_map_position += acc0.InputSRAMWidth // config.DATA_WIDTH + config.BUS_WIDTH // config.DATA_WIDTH #补偿最后一次多减了一个
            if i_rows % rows_per_input_channel == rows_per_input_channel - 1:
                input_map_position += input_map_length - rows_per_input_channel * acc0.InputSRAMWidth // config.DATA_WIDTH 
    return input_map_position
        
def WU_LSBANK(num_ls, num_channel, i_block): #输入要存几个channel，几个local switch，从第几个block开始，注：在wsap下block按行输入，
    with open('wsap.log','a') as f:
        for i_ls in range(num_ls):
            i_pt = i_block // weight_block_col
            i_at = i_block % weight_block_col
            for j_channel in range(num_channel):
                i_weight_channel = i_pt * config.PC + j_channel
                j_data_in_channel = i_at * config.AL
                weight_map_position = i_weight_channel * weight_map_length + j_data_in_channel
                for k_reg in reversed(range(acc0.CIMsWriteWidth//acc0.BusWidth*config.WEIGHT_ROW)):
                    row_reg = (acc0.CIMsWriteWidth//acc0.BusWidth*config.WEIGHT_ROW - 1 - k_reg) // (acc0.CIMsWriteWidth//acc0.BusWidth)
                    pause_reg = k_reg % (acc0.CIMsWriteWidth//acc0.BusWidth)
                    if pause_reg == 0:
                        f.write("wu\t"+str(k_reg)+"\t"+str(j_channel*config.SCR*config.WEIGHT_ROW+row_reg*config.SCR+i_ls)+
                                "\t" + str(weight_map_position)+"\n")
                    else:
                        f.write("wup\t"+str(k_reg)+"\t"+str(j_channel*config.SCR*config.WEIGHT_ROW+row_reg*config.SCR+i_ls)+
                                "\t" + str(weight_map_position)+"\n")
            i_block += 1

def COMPUTE(i_input_channel, computing_block):# 输入channel, computing block, 对当前channel内所有内容遍历CIM进行计算
    # bit-parallel
    i_ls = computing_block % config.SCR
    i_pt = computing_block // weight_block_col
    i_at = computing_block % weight_block_col
    # atos_flag = int(atos_matrix[i_pt,i_at])
    atos_flag = atos_dict[int(atos_matrix[i_pt,i_at].item())]
    os_addr = i_input_channel * para_times + i_pt
    is_addr = i_input_channel * rows_per_input_channel + i_at
    if atos_matrix[i_pt,i_at] == 0:
        write_status = 0
    elif os_addr % 2 == 1:
        write_status = 1
    else:
        write_status = 2

    if atos_matrix[i_pt,i_at] != 2 :
        n = 0
    else:
        n = ws_history.find_last_different_status(write_status)
    
    if n != 0:
        read_command = "read_OS_line "+str(os_addr)
        add_read_n_lines_before('wsap.log', n, read_command)

    with open('wsap.log','a') as f:
        if i_input_channel < input_channels_per_ISload:
            f.write("cmpfis\t" + str(is_addr) + '\t' + str(i_ls) + '\t' + str(atos_flag) + '\t' +str(os_addr) + '\n')
                    # + '\t' + "ws = " + str(write_status) + '\t' + "n = " + str(n) + '\n')
        else:
            input_map_position = i_input_channel * input_map_length + i_at * config.AL + int(config.BUS_WIDTH / config.DATA_WIDTH) * (acc0.InputSRAMWidth//acc0.BusWidth - 1)
            for j_reg in reversed(range(acc0.InputSRAMWidth//acc0.BusWidth)):
                if j_reg != 0:
                    f.write("cmpgtp\t" + str(i_ls) + '\t' + str(atos_flag) + '\t' +str(os_addr)+ '\t' 
                            +str(j_reg)+ '\t' +str(input_map_position)+"\n")
                else:
                    f.write("cmpgt\t" + str(i_ls) + '\t' + str(atos_flag) + '\t' +str(os_addr)+ '\t' 
                            +str(j_reg)+ '\t' +str(input_map_position)+"\n")
                input_map_position -= int(config.BUS_WIDTH / config.DATA_WIDTH)
    ws_history.update("write_status") 


LOG_INIT()
i_block = 0
ws_history = write_history.WriteStatusHistory()
LOADIS_BLOCK(num_rows = rows_per_input_channel * input_channels_per_ISload, input_map_position = 0)
for i_weight_update in range(weight_update_times_per_inst):
    WU_LSBANK(num_ls = weight_update_ls[i_weight_update], 
                num_channel = config.PC,  # !!!可能有很多channel浪费
                i_block = i_block)
    for i in range (acc0.CIMsWriteWidth//acc0.BusWidth*config.WEIGHT_ROW):
        IDLE()
    
    for j_ls in range(weight_update_ls[i_weight_update]): #选中一个ls
        j_compute_block = i_block + j_ls
        for i_input_channel in range(input_map_channel):
            COMPUTE(i_input_channel = i_input_channel, 
                    computing_block = j_compute_block)
    i_block += weight_update_ls[i_weight_update]

# !!! 以下为测试用输出，勿删

print("System config:")
for attr, value in config.__dict__.items():
    print(f"{attr} = {value}")

print("\nHardware config:")
for attr, value in acc0.__dict__.items():
    print(f"{attr} = {value}")

print("\nInput map mapping:")
print(f"input_data_per_row = {input_data_per_row}")
print(f"rows_per_input_channel = {rows_per_input_channel}")
print(f"input_channels_per_ISload = {input_channels_per_ISload}")

print("\nWeight map mapping:")
print(f"weight_block_row = {weight_block_row}")
print(f"weight_block_col = {weight_block_col}")
print(f"weight_block_num = {weight_block_num}")
print(f"weight_update_times_per_inst = {weight_update_times_per_inst}")
        
print(f"weight_update_ls = {weight_update_ls}")
        
print("ls_matrix:\n", ls_matrix, "\n")
print("atos_matrix:\n", atos_matrix, "\n")