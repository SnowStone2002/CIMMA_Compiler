# Micro Instruction Compiler
# Input: hardware config, graph level instruction
# Output: micro instructions

# datatype: INT8
# CIM is bit parallel

# Mode - ISAP

from hw_config import hwc
from hw_config import Config
import write_history 
from append_read import add_read_n_lines_before
import math as m
import torch
from inst_stack import inst_stack
import os

# 可变参数
config = Config(al=64, pc=16, scr=4, bus_width=128, is_depth=32, os_depth=1)
acc0 = hwc(config)
gli = ['mvm', (55, 1024, 64)]

# 两个length对应作点乘，channel互相无关
weight_map_channel = gli[1][0]
weight_map_length = gli[1][1]

input_map_length  = gli[1][1]
input_map_channel  = gli[1][2]

# 计算input map到IS的mapping
# region 对于Input_map 到 IS 的 mapping, 我们首先需要将一个channel的数据放入IS，如果一个channel放完，IS当前行未满，则后续补0，新的channel另起一行
input_data_per_row = m.floor(acc0.InputSRAMWidth / config.DATA_WIDTH)
rows_per_input_channel = m.ceil(input_map_length / input_data_per_row)
input_channels_per_ISload = m.floor(acc0.InputSRAMDepth / rows_per_input_channel)
IS_load_times_per_inst = m.ceil(input_map_channel / input_channels_per_ISload)

IS_load_rows = [input_channels_per_ISload * rows_per_input_channel] * (IS_load_times_per_inst)
if input_map_channel % input_channels_per_ISload != 0:
    IS_load_rows[IS_load_times_per_inst-1] = input_map_channel % input_channels_per_ISload * rows_per_input_channel
# endregin

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
    os.remove(r'mi.log')
    if VERIFY == 1:
        with open('mi.log','w') as f:
            f.write("starting compiler:\n")
    else:
        stk.push("starting compiler:\n")

def IDLE():
    if VERIFY == 1:
        with open('mi.log','a') as f:
            f.write("nop\n")
    else:
        stk.push("nop\n")

def LOADIS_BLOCK(num_rows, input_map_position): #输入现在正要存的数据在input map中的位置，以及需要输入多少行
    with open('mi.log','a') as f:
        for i_rows in range(num_rows):
            input_map_position += int(config.BUS_WIDTH / config.DATA_WIDTH) * (acc0.InputSRAMWidth//acc0.BusWidth - 1)
            for j_reg in reversed(range(acc0.InputSRAMWidth//acc0.BusWidth)):
                if j_reg != 0:
                    if VERIFY == 1:
                        f.write("lisp\t"+str(j_reg)+"\t"+str(i_rows)+"\t"+str(input_map_position)+"\n")
                    else:
                        #f.write("lis_p\t <pos> "+str(j_reg)+"\t <is_addr> "+str(i_rows)+"\n")
                        stk.push(inst="lis_p\t <pos> "+str(j_reg)+"\t <is_addr> "+str(i_rows)+"\n")
                else:
                    if VERIFY == 1:
                        f.write("lis\t\t"+str(j_reg)+"\t"+str(i_rows)+"\t"+str(input_map_position)+"\n")
                    else:
                        # f.write("lis\t\t <pos> "+str(j_reg)+"\t <is_addr> "+str(i_rows)+"\n")
                        stk.push(inst="lis\t\t <pos> "+str(j_reg)+"\t <is_addr> "+str(i_rows)+"\n")

                input_map_position -= int(config.BUS_WIDTH / config.DATA_WIDTH)
                # !!! 每一个channel的最后一行，可能要填0
            input_map_position += int(acc0.InputSRAMWidth / config.DATA_WIDTH) + int(config.BUS_WIDTH / config.DATA_WIDTH)
    return input_map_position

def WU_LSBANK(num_ls, num_channel, i_block): #输入要存几个channel，几个local switch，从第几个block开始，注：在isap下block按行输入，
    with open('mi.log','a') as f:
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
                        if VERIFY == 1:
                            f.write("wu\t"+str(k_reg)+"\t"+str(j_channel*config.SCR*config.WEIGHT_ROW+row_reg*config.SCR+i_ls)+
                                "\t" + str(weight_map_position)+"\n")
                        else:
                            # f.write("wu\t\t <pos> "+str(k_reg%(acc0.CIMsWriteWidth//acc0.BusWidth))+"\t <cm_addr> "+str(j_channel*config.SCR*config.WEIGHT_ROW+row_reg*config.SCR+i_ls)+"\n")
                            stk.push(inst="wu\t\t <pos> "+str(k_reg%(acc0.CIMsWriteWidth//acc0.BusWidth))+"\t <cm_addr> "+str(j_channel*config.SCR*config.WEIGHT_ROW+row_reg*config.SCR+i_ls)+"\n")
                    else:
                        if VERIFY == 1:
                            f.write("wup\t"+str(k_reg)+"\t"+str(j_channel*config.SCR*config.WEIGHT_ROW+row_reg*config.SCR+i_ls)+
                                "\t" + str(weight_map_position)+"\n")
                        else:
                            #f.write("wu_p\t <pos> "+str(k_reg%(acc0.CIMsWriteWidth//acc0.BusWidth))+"\t <cm_addr> "+str(j_channel*config.SCR*config.WEIGHT_ROW+row_reg*config.SCR+i_ls)+"\n")
                            stk.push(inst="wu_p\t <pos> "+str(k_reg%(acc0.CIMsWriteWidth//acc0.BusWidth))+"\t <cm_addr> "+str(j_channel*config.SCR*config.WEIGHT_ROW+row_reg*config.SCR+i_ls)+"\n")
            i_block += 1

def CMP(i_input_channel, computing_block):# 输入channel, computing block, 对当前channel内所有内容遍历CIM进行计算
    # bit-parallel
    i_ls = computing_block % config.SCR
    i_pt = computing_block // weight_block_col
    i_at = computing_block % weight_block_col
    # atos_flag = int(atos_matrix[i_pt,i_at])
    atos_flag = atos_dict[int(atos_matrix[i_pt,i_at].item())]
    os_addr = i_input_channel * para_times + i_pt
    is_addr = i_input_channel % input_channels_per_ISload * rows_per_input_channel + i_at
    #if atos_matrix[i_pt,i_at] == 0:
    #    write_status = 0
    #elif os_addr % 2 == 1:
    #    write_status = 1
    #else:
    #    write_status = 2

    #if atos_matrix[i_pt,i_at] != 2 :
    #    n = 0
    #else:
    #    n = ws_history.find_last_different_status(write_status)
    
    #if n != 0:
    #    read_command = "<os_addr_rd> "+str(os_addr)
    #    add_read_n_lines_before('mi.log', n, read_command)

    with open('mi.log','a') as f:
        global os_virtual_depth

        if VERIFY == 1:
            f.write("cmpfis_int8\t" + str(is_addr) + '\t' + str(i_ls) + '\t' + str(atos_flag) + '\t' +str(os_addr) + '\n')
                # + '\t' + "ws = " + str(write_status) + '\t' + "n = " + str(n) + '\n')
        else:

            #f.write("cmpfis\t <is_addr> " + str(is_addr) + '\t <ca> ' + str(i_ls) + '\t <' + str(atos_flag) + '>\t <os_addr> ' +str(os_addr) + '\n')
            if atos_flag == 'aos': # aos 
                if os_addr > os_virtual_depth: # aos, os overflow
                    if i_at == acc_times-1: # complete one output, gen rd request, aos: paos(go through)
                        os_virtual_depth += 1
                    stk.push(inst="pload\t\n")
                    stk.push(inst="cmpfis\t <is_addr> " + str(is_addr) + '\t <ca> ' + str(i_ls) + '\t <paos>'+ '\n')
                else: # aos, os not overflow
                    if i_at == acc_times-1: # complete one output, gen rd request, aos: paos(go through)
                        os_virtual_depth += 1
                        stk.push(inst="cmpfis\t <is_addr> " + str(is_addr) + '\t <ca> ' + str(i_ls) + '\t <paos>' + '\n', rd_req = 1, rd_addr = os_addr) # virtual -> practical?
                    else: # gen aos rd request
                        stk.push(inst="cmpfis\t <is_addr> " + str(is_addr) + '\t <ca> ' + str(i_ls) + '\t <' + str(atos_flag) + '>\t <os_addr_wt> ' +str(os_addr) + '\n', rd_req = 1, rd_addr = os_addr) 

            elif atos_flag == 'tos': # tos
                if os_addr > os_virtual_depth: # tos, os overflow
                    if i_at == acc_times-1: # complete one output, gen rd request, aos: paos(go through)
                        os_virtual_depth += 1
                    stk.push(inst="cmpfis\t <is_addr> " + str(is_addr) + '\t <ca> ' + str(i_ls) + '\t <ptos>' + '\n')
                else: # tos, os not overflow
                    if i_at == acc_times-1: #gen rd request
                        os_virtual_depth += 1
                        stk.push(inst="cmpfis\t <is_addr> " + str(is_addr) + '\t <ca> ' + str(i_ls) + '\t <ptos> ' + '\n')
                    else: # tos
                        stk.push(inst="cmpfis\t <is_addr> " + str(is_addr) + '\t <ca> ' + str(i_ls) + '\t <' + str(atos_flag) + '>\t <os_addr_wt> ' +str(os_addr) + '\n')
            
            else: # aor
                stk.push(inst="cmpfis\t <is_addr> " + str(is_addr) + '\t <ca> ' + str(i_ls) + '\t <' + str(atos_flag) + '>\n')


# ws_history.update("write_status") 


# region isap
def ISAP():
    input_map_position = 0 
    for i_IS_load in range(IS_load_times_per_inst):
        input_map_position = LOADIS_BLOCK(num_rows = IS_load_rows[i_IS_load], 
                                        input_map_position = input_map_position)

        i_block = 0

        for j_weight_load in range(weight_update_times_per_inst):
            WU_LSBANK(num_ls = weight_update_ls[j_weight_load], 
                    num_channel = config.PC,  # !!!可能有很多channel浪费
                    i_block = i_block)
            
            for i in range (acc0.CIMsWriteWidth//acc0.BusWidth*config.WEIGHT_ROW):
                IDLE()

            for i_input_channel in range(i_IS_load * input_channels_per_ISload, 
                                        i_IS_load * input_channels_per_ISload + 
                                        IS_load_rows[i_IS_load] // rows_per_input_channel): # 选中一个input channel
                for j_ls in range(weight_update_ls[j_weight_load]): #选中一个ls
                    j_compute_block = i_block + j_ls
                    CMP(i_input_channel = i_input_channel, 
                        computing_block = j_compute_block)

            i_block += weight_update_ls[j_weight_load]
# endregion


# stack for os read optimization
fifo_len = 1
stk = inst_stack(fifo_len)

# for os_overflow penalty
os_virtual_depth = acc0.OutputSRAMDepth

VERIFY = 0 
LOG_INIT()
#ws_history = write_history.WriteStatusHistory()
ISAP()
for i in range(fifo_len):
    stk.push()




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
print(f"IS_load_times_per_inst = {IS_load_times_per_inst}")
    
print(f"IS_load_rows = {IS_load_rows}")

print("\nWeight map mapping:")
print(f"weight_block_row = {weight_block_row}")
print(f"weight_block_col = {weight_block_col}")
print(f"weight_block_num = {weight_block_num}")
print(f"weight_update_times_per_inst = {weight_update_times_per_inst}")
        
print(f"weight_update_ls = {weight_update_ls}")
        
print("ls_matrix:\n", ls_matrix, "\n")
print("atos_matrix:\n", atos_matrix, "\n")
