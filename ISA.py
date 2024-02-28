ISA format

total length: 43



LoadISP/LoadIS:



lis:
lis + reg_position(0/1/2/3) + IS_addr(address 0-) + input_map_position

input_map_position = i_input_channel * input_map_length + i_reg * BusWidth


wu:
wu + reg_position(0/1/2/3) + CIMaddress + weight_map_postion

CIM address = i_pc * PC宽度 + i_reg * SCR宽度 + scr_num
weight_map_position = i_channel + i_data


cmpfis:
cmpfis + IS_addr + ls + atos + OS_addr

os_addr = i_input_channel * weight_channel + i_weight_channel

0:aor reg = reg + psum
1:tos OS = reg + psum, reg = 0
2:aos OS = psum + reg + OS, reg = 0


任务：
1 创建git repo
2 compiler生成机器码
3 reg的值改动为倒序
4 改wu load的长度bug