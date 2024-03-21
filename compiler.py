from hw_config import hwc, Config
import math as m
import torch
from inst_stack import inst_stack
import os

class MicroInstructionCompiler:
    def __init__(self, config, gli, data_stream, VERIFY=False):
        self.config = config
        self.gli = gli
        self.data_stream = data_stream
        self.VERIFY = VERIFY
        self.acc0 = hwc(config)
        self.init_mappings()
        self.init_matrices()
        self.os_virtual_depth = self.acc0.OutputSRAMDepth
        self.gt_in_map_record = 0
        self.fifo_len = 100
        self.stk = inst_stack(filename="./cflow/"+data_stream+".log", len=self.fifo_len)  # Example size, adjust as needed
        
    def init_mappings(self):
        # Initialize mappings here (e.g., input_map, weight_map)
        gli = self.gli
        config = self.config
        # 两个length对应作点乘，channel互相无关
        self.weight_map_channel = gli[1][0]
        self.weight_map_length = gli[1][1]

        self.input_map_length  = gli[1][1]
        self.input_map_channel  = gli[1][2]

        # 计算input map到IS的mapping
        # region 对于Input_map 到 IS 的 mapping, 我们首先需要将一个channel的数据放入IS，如果一个channel放完，IS当前行未满，则后续补0，新的channel另起一行
        self.input_data_per_row = m.floor(self.acc0.InputSRAMWidth / config.DATA_WIDTH)
        self.rows_per_input_channel = m.ceil(self.input_map_length / self.input_data_per_row)
        self.input_channels_per_ISload = min(self.acc0.InputSRAMDepth // self.rows_per_input_channel, self.input_map_channel)
        self.IS_load_times_per_inst = m.ceil(self.input_map_channel / self.input_channels_per_ISload)

        self.IS_load_rows = [self.input_channels_per_ISload * self.rows_per_input_channel] * (self.IS_load_times_per_inst)
        if self.input_map_channel % self.input_channels_per_ISload != 0:
            self.IS_load_rows[self.IS_load_times_per_inst-1] = self.input_map_channel % self.input_channels_per_ISload * self.rows_per_input_channel
        # endregion

        # region 将weight map切成CIM size的block，放入CIM中
        self.weight_block_row = m.ceil(self.weight_map_channel / config.PC)
        self.weight_block_col = m.ceil(self.weight_map_length / config.AL)
        self.weight_block_num = self.weight_block_col * self.weight_block_row
        self.weight_update_times_per_inst = m.ceil(self.weight_block_num / config.SCR)

        self.weight_update_ls = [config.SCR] * self.weight_update_times_per_inst
        if self.weight_block_num % config.SCR != 0:
            self.weight_update_ls[self.weight_update_times_per_inst-1] = self.weight_block_num % config.SCR
        # endregion

        self.para_times = self.weight_block_row
        self.acc_times = self.weight_block_col

        self.weight_map_channel = self.para_times * config.PC
        self.weight_map_length = self.acc_times * config.AL

        self.input_map_length  = self.acc_times * config.AL
        self.input_map_channel  = self.input_map_channel

    def init_matrices(self):
        config = self.config
        # Initialize ls_matrix and atos_matrix here
        para_times = self.para_times
        acc_times = self.acc_times
        # ls代表了每一次cim计算local switch的状态（用第几个存储的数据做计算）
        ls_matrix = torch.zeros(self.para_times,self.acc_times) # local switch
        ls_fg = 0
        aor, tos, aos = 0, 1, 2
        self.atos_dict = ['aor','tos','aos']
        atos_matrix = torch.zeros(para_times,acc_times)
        # atos matrix 代表了这一次计算的外部数据流方向
            # 0:aor reg = reg + psum
            # 1:tos OS = reg + psum, reg = 0
            # 2:aos OS = psum + reg + OS, reg = 0

        if self.data_stream == 'isap' or self.data_stream == 'wsap': # ap 优先acc
            for i_pt in range(para_times):
                for i_at in range(acc_times):
                    ls_matrix[i_pt,i_at] = ls_fg
                    ls_fg = ls_fg+1
                    if ls_fg == config.SCR: ls_fg = 0
            for i_pt in range(para_times):
                row_st_fg = 0 # row start flag
                for i_at in range(acc_times):    
                    if i_at == acc_times-1 or ls_matrix[i_pt,i_at] == self.acc0.LocalSwitchrows - 1:
                        if row_st_fg == 0: 
                            atos_matrix[i_pt,i_at] = tos
                            row_st_fg = 1
                        else:
                            atos_matrix[i_pt,i_at] = aos

        elif self.data_stream == 'ispp' or self.data_stream == 'wspp':   # pp 有限para
            for i_at in range(acc_times):
                for i_pt in range(para_times):
                    ls_matrix[i_pt,i_at] = ls_fg
                    ls_fg = ls_fg+1
                    if ls_fg == config.SCR: ls_fg = 0
            for i_pt in range(para_times):
                for i_at in range(acc_times):    
                    if i_at == 0: 
                        atos_matrix[i_pt,i_at] = tos
                    else:
                        atos_matrix[i_pt,i_at] = aos

        self.ls_matrix = ls_matrix
        self.atos_matrix = atos_matrix

    def log_init(self):
        # Log initialization logic here
        if os.path.exists("./cflow/"+self.data_stream+".log"):
            os.remove(r"./cflow/"+self.data_stream+".log")
        self.stk.push("starting compiler:\n")

    def idle(self):
        # Idle instruction logic here
        self.stk.push("Nop\n")

    def load_is_block(self, num_rows, input_map_position):
        # Logic for loading IS block
        acc0 = self.acc0
        config = self.config
        with open("./cflow/"+self.data_stream+".log",'a') as f:
            for i_rows in range(num_rows):
                input_map_position += int(config.BUS_WIDTH / config.DATA_WIDTH) * (acc0.InputSRAMWidth//acc0.BusWidth - 1)
                for j_reg in reversed(range(acc0.InputSRAMWidth//acc0.BusWidth)):
                    if j_reg != 0:
                        if self.VERIFY:
                            self.stk.push(inst="Linp\t <pos> "+str(j_reg)+"\t <is_addr> "+str(i_rows)+
                                    "\t <input_map> "+str(input_map_position)+"\n")
                        else:
                            self.stk.push(inst="Linp\t <pos> "+str(j_reg)+"\n")
                    else:
                        if self.VERIFY:
                            self.stk.push(inst="Lin\t\t <pos> "+str(j_reg)+"\t <is_addr> "+str(i_rows)+
                                    "\t <input_map> "+str(input_map_position)+"\n")
                        else:
                            self.stk.push(inst="Lin\t\t <pos> "+str(j_reg)+"\t <is_addr> "+str(i_rows)+"\n")
                    input_map_position -= int(config.BUS_WIDTH / config.DATA_WIDTH)
                    # !!! 每一个channel的最后一行，可能要填0
                input_map_position += int(acc0.InputSRAMWidth / config.DATA_WIDTH) + int(config.BUS_WIDTH / config.DATA_WIDTH)
        return input_map_position
    
    def wu_ls_bank(self, num_ls, num_channel, i_block):
        # Logic for weight update in LS bank
        acc0 = self.acc0
        config = self.config
        with open("./cflow/"+self.data_stream+".log",'a') as f:
            for i_ls in range(num_ls):
                if self.data_stream == 'isap' or self.data_stream == 'wsap':
                    i_pt = i_block // self.weight_block_col
                    i_at = i_block % self.weight_block_col
                elif self.data_stream == 'ispp' or self.data_stream == 'wspp':
                    i_pt = i_block % self.weight_block_row
                    i_at = i_block // self.weight_block_row
                for j_channel in range(num_channel):
                    i_weight_channel = i_pt * config.PC + j_channel
                    j_data_in_channel = i_at * config.AL
                    weight_map_position = i_weight_channel * self.weight_map_length + j_data_in_channel
                    for k_reg in reversed(range(acc0.CIMsWriteWidth//acc0.BusWidth*config.WEIGHT_ROW)):
                        weight_map_position = i_weight_channel *self. weight_map_length + j_data_in_channel + k_reg * acc0.BusWidth // config.DATA_WIDTH
                        row_reg = (acc0.CIMsWriteWidth//acc0.BusWidth*config.WEIGHT_ROW - 1 - k_reg) // (acc0.CIMsWriteWidth//acc0.BusWidth)
                        pause_reg = k_reg % (acc0.CIMsWriteWidth//acc0.BusWidth)
                        if pause_reg == 0:
                            if self.VERIFY:
                                self.stk.push(inst="Lwt\t\t <pos> "+str(k_reg%(acc0.CIMsWriteWidth//acc0.BusWidth))+"\t <cm_addr> "+str(j_channel*config.SCR*config.WEIGHT_ROW+row_reg*config.SCR+i_ls)+
                                        "\t <weight_map> "+str(weight_map_position)+"\n")
                            else:
                                self.stk.push(inst="Lwt\t\t <pos> "+str(k_reg%(acc0.CIMsWriteWidth//acc0.BusWidth))+"\t <cm_addr> "+str(j_channel*config.SCR*config.WEIGHT_ROW+row_reg*config.SCR+i_ls)+"\n")
                        else:
                            if self.VERIFY:
                                self.stk.push(inst="Lwtp\t <pos> "+str(k_reg%(acc0.CIMsWriteWidth//acc0.BusWidth))+"\t <cm_addr> "+str(j_channel*config.SCR*config.WEIGHT_ROW+row_reg*config.SCR+i_ls)+
                                        "\t <weight_map> "+str(weight_map_position)+"\n")
                            else:
                                self.stk.push(inst="Lwtp\t <pos> "+str(k_reg%(acc0.CIMsWriteWidth//acc0.BusWidth))+"\n")
                i_block += 1

    def compute(self, i_input_channel, computing_block):
        # Compute logic for input channel and computing block
        acc0 = self.acc0
        config = self.config
        i_ls = computing_block % config.SCR
        if self.data_stream == 'isap' or self.data_stream == 'wsap':
            i_pt = computing_block // self.weight_block_col
            i_at = computing_block % self.weight_block_col
        elif self.data_stream == 'ispp' or self.data_stream == 'wspp':
            i_pt = computing_block % self.weight_block_row
            i_at = computing_block // self.weight_block_row
        
        atos_flag   =   self.atos_dict[int(self.atos_matrix[i_pt,i_at].item())]
        os_addr     =   i_input_channel * self.para_times + i_pt

        if self.data_stream == 'isap' or self.data_stream == 'ispp':
            is_addr = i_input_channel % self.input_channels_per_ISload * self.rows_per_input_channel + i_at
        elif self.data_stream == 'wsap' or self.data_stream == 'wspp':
            is_addr = i_input_channel * self.rows_per_input_channel + i_at

        with open("./cflow/"+self.data_stream+".log",'a') as f:
            
            if ((self.data_stream == 'wsap' or self.data_stream == 'wspp') and (i_input_channel >= self.input_channels_per_ISload)):
                input_map_position = i_input_channel * self.input_map_length + i_at * config.AL + int(config.BUS_WIDTH / config.DATA_WIDTH) * (acc0.InputSRAMWidth//acc0.BusWidth - 1)
                for j_reg in reversed(range(acc0.InputSRAMWidth//acc0.BusWidth)):
                    # print("input_map_position=",input_map_position,"gt_in_map_record=",self.gt_in_map_record)
                    if (self.gt_in_map_record // (acc0.InputSRAMWidth // config.DATA_WIDTH) == input_map_position // (acc0.InputSRAMWidth // config.DATA_WIDTH)) and (j_reg != 0):
                        input_map_position -= int(config.BUS_WIDTH / config.DATA_WIDTH)
                        continue
                    if (j_reg != 0):  # Cmpfgtp
                        if self.VERIFY:
                            self.stk.push(inst="Cmpfgtp\t " + "<pos> \t" + str(j_reg) + "\t<input_map_position>\t" + str(input_map_position) + '\n')
                        else:
                            self.stk.push(inst="Cmpfgtp\t " + "<pos> \t" + str(j_reg)+ '\n')
                        input_map_position -= int(config.BUS_WIDTH / config.DATA_WIDTH)
                    else:           # Cmpfgt
                        if atos_flag == 'aos': # aos 
                            if os_addr > self.os_virtual_depth: # aos, os overflow
                                if i_at == self.acc_times-1: # complete one output, gen rd request, aos: paos(go through)
                                    self.os_virtual_depth += 1
                                if self.VERIFY:
                                    self.stk.push(inst="Lpenalty\t" + "<os_addr_rd>\t" + str(os_addr) + '\n')
                                    self.stk.push(inst="Cmpfgt" + "\t <pos> \t" + str(j_reg) + "\t<input_map_position>\t" + str(input_map_position) + '\t <ca> ' + str(i_ls) + '\t <paos>' + '\t <os_addr_wt> ' + str(os_addr) + 
                                            '\n')
                                else:
                                    for i in range (acc0.OutputSRAMWidth// (config.RESULT_WIDTH // config.DATA_WIDTH) // config.BUS_WIDTH):
                                        self.stk.push(inst="Lpenalty\t\n")
                                    self.stk.push(inst="Cmpfgt" + "\t <pos> \t" + str(j_reg) + '\t <ca> ' + str(i_ls) + '\t <paos>' + 
                                            '\n')
                            else: # aos, os not overflow
                                if i_at == self.acc_times-1: # complete one output, gen rd request, aos: paos(go through)
                                    self.os_virtual_depth += 1
                                    if self.VERIFY:
                                        self.stk.push(inst="Cmpfgt" + "\t <pos> \t" + str(j_reg) + "\t<input_map_position>\t" + str(input_map_position) + '\t <ca> ' + str(i_ls) + '\t <paos>' + '\t <os_addr_wt> ' + str(os_addr) + 
                                                '\n', rd_req = 1, rd_addr = os_addr) # virtual -> practical?
                                    else:
                                        self.stk.push(inst="Cmpfgt" + "\t <pos> \t" + str(j_reg) + '\t <ca> ' + str(i_ls) + '\t <paos>' + 
                                                '\n', rd_req = 1, rd_addr = os_addr) # virtual -> practical?
                                else: # gen aos rd request
                                    if self.VERIFY:
                                        self.stk.push(inst="Cmpfgt" + "\t <pos> \t" + str(j_reg) + "\t<input_map_position>\t" + str(input_map_position) + '\t <ca> ' + str(i_ls) + '\t <' + str(atos_flag) + '>\t <os_addr_wt> ' + str(os_addr) + 
                                                '\n', rd_req = 1, rd_addr = os_addr) 
                                    else:
                                        self.stk.push(inst="Cmpfgt" + "\t <pos> \t" + str(j_reg) + '\t <ca> ' + str(i_ls) + '\t <' + str(atos_flag) + '>\t <os_addr_wt> ' + str(os_addr) + 
                                                '\n', rd_req = 1, rd_addr = os_addr) 

                        elif atos_flag == 'tos': # tos
                            if os_addr > self.os_virtual_depth: # tos, os overflow
                                if i_at == self.acc_times-1: # complete one output, gen rd request, aos: paos(go through)
                                    self.os_virtual_depth += 1
                                if self.VERIFY:
                                    self.stk.push(inst="Cmpfgt" + "\t <pos> \t" + str(j_reg) + "\t<input_map_position>\t" + str(input_map_position) + '\t <ca> ' + str(i_ls) + '\t <ptos>' + '\t <os_addr_wt> ' + str(os_addr) + 
                                            '\n')
                                else:
                                    self.stk.push(inst="Cmpfgt" + "\t <pos> \t" + str(j_reg) + '\t <ca> ' + str(i_ls) + '\t <ptos>' + 
                                            '\n')
                            else: # tos, os not overflow
                                if i_at == self.acc_times-1: #gen rd request
                                    self.os_virtual_depth += 1
                                    if self.VERIFY:
                                        self.stk.push(inst="Cmpfgt" + "\t <pos> \t" + str(j_reg) + "\t<input_map_position>\t" + str(input_map_position) + '\t <ca> ' + str(i_ls) + '\t <ptos> ' + '\t <os_addr_wt> ' + str(os_addr) + 
                                                '\n')
                                    else:
                                        self.stk.push(inst="Cmpfgt" + "\t <pos> \t" + str(j_reg) + '\t <ca> ' + str(i_ls) + '\t <ptos> ' + 
                                                '\n')
                                else: # tos
                                    if self.VERIFY:
                                        self.stk.push(inst="Cmpfgt" + "\t <pos> \t" + str(j_reg) + "\t<input_map_position>\t" + str(input_map_position) + '\t <ca> ' + str(i_ls) + '\t <' + str(atos_flag) + '>\t <os_addr_wt> ' +str(os_addr) + 
                                                '\n')
                                    else:
                                        self.stk.push(inst="Cmpfgt" + "\t <pos> \t" + str(j_reg) + '\t <ca> ' + str(i_ls) + '\t <' + str(atos_flag) + '>\t <os_addr_wt> ' +str(os_addr) + 
                                                '\n')
                        
                        else: # aor
                            if self.VERIFY:
                                self.stk.push(inst="Cmpfgt" + '\t <ca> ' + str(i_ls) + '\t <' + str(atos_flag) + 
                                        ">\t <pos> \t" + str(j_reg) + "\t<input_map_position>\t" + str(input_map_position) + '\n')
                            else:
                                self.stk.push(inst="Cmpfgt" + '\t <ca> ' + str(i_ls) + '\t <' + str(atos_flag) + 
                                        ">\t <pos> \t" + str(j_reg) + '\n')

                    # input_map_position -= int(config.BUS_WIDTH / config.DATA_WIDTH)

                self.gt_in_map_record = input_map_position# + int(config.BUS_WIDTH / config.DATA_WIDTH)

            else: # is or (ws & i_input_channel < input_channels_per_ISload)
                if atos_flag == 'aos': # aos 
                    if os_addr > self.os_virtual_depth: # aos, os overflow
                        if i_at == self.acc_times-1: # complete one output, gen rd request, aos: paos(go through)
                            self.os_virtual_depth += 1
                        if self.VERIFY:
                            self.stk.push(inst="Lpenalty\t" + "<os_addr_rd>\t" + str(os_addr) + '\n')
                            self.stk.push(inst="Cmpfis\t <is_addr> " + str(is_addr) + '\t <ca> ' + str(i_ls) + '\t <paos>' + '\t <os_addr_wt> ' + str(os_addr) + '\n')
                        else:
                            for i in range (acc0.OutputSRAMWidth// (config.RESULT_WIDTH // config.DATA_WIDTH) // config.BUS_WIDTH):
                                self.stk.push(inst="Lpenalty\t\n")
                            self.stk.push(inst="Cmpfis\t <is_addr> " + str(is_addr) + '\t <ca> ' + str(i_ls) + '\t <paos>' + '\n')
                    else: # aos, os not overflow
                        if i_at == self.acc_times-1: # complete one output, gen rd request, aos: paos(go through)
                            self.os_virtual_depth += 1
                            if self.VERIFY:
                                self.stk.push(inst="Cmpfis\t <is_addr> " + str(is_addr) + '\t <ca> ' + str(i_ls) + '\t <paos>' + '\t <os_addr_wt> ' + str(os_addr) + '\n', rd_req = 1, rd_addr = os_addr) # virtual -> practical?
                            else:
                                self.stk.push(inst="Cmpfis\t <is_addr> " + str(is_addr) + '\t <ca> ' + str(i_ls) + '\t <paos>' + '\n', rd_req = 1, rd_addr = os_addr) # virtual -> practical?
                        else: # gen aos rd request
                            self.stk.push(inst="Cmpfis\t <is_addr> " + str(is_addr) + '\t <ca> ' + str(i_ls) + '\t <' + str(atos_flag) + '>\t <os_addr_wt> ' +str(os_addr) + '\n', rd_req = 1, rd_addr = os_addr) 

                elif atos_flag == 'tos': # tos
                    if os_addr > self.os_virtual_depth: # tos, os overflow
                        if i_at == self.acc_times-1: # complete one output, gen rd request, aos: paos(go through)
                            self.os_virtual_depth += 1
                        if self.VERIFY:
                            self.stk.push(inst="Cmpfis\t <is_addr> " + str(is_addr) + '\t <ca> ' + str(i_ls) + '\t <ptos>' + '\t <os_addr_wt> ' + str(os_addr) + '\n')
                        else:
                            self.stk.push(inst="Cmpfis\t <is_addr> " + str(is_addr) + '\t <ca> ' + str(i_ls) + '\t <ptos>' + '\n')
                    else: # tos, os not overflow
                        if i_at == self.acc_times-1: #gen rd request
                            self.os_virtual_depth += 1
                            if self.VERIFY:
                                self.stk.push(inst="Cmpfis\t <is_addr> " + str(is_addr) + '\t <ca> ' + str(i_ls) + '\t <ptos> ' + '\t <os_addr_wt> ' + str(os_addr) + '\n')
                            else:
                                self.stk.push(inst="Cmpfis\t <is_addr> " + str(is_addr) + '\t <ca> ' + str(i_ls) + '\t <ptos> ' + '\n')
                        else: # tos
                            self.stk.push(inst="Cmpfis\t <is_addr> " + str(is_addr) + '\t <ca> ' + str(i_ls) + '\t <' + str(atos_flag) + '>\t <os_addr_wt> ' +str(os_addr) + '\n')
                
                else: # aor
                    self.stk.push(inst="Cmpfis\t <is_addr> " + str(is_addr) + '\t <ca> ' + str(i_ls) + '\t <' + str(atos_flag) + '>\n')

    def is_process(self):
        # Processing logic for IS
        acc0 = self.acc0
        config = self.config
        input_map_position = 0 
        for i_IS_load in range(self.IS_load_times_per_inst):
            input_map_position = self.load_is_block(num_rows = self.IS_load_rows[i_IS_load], 
                                            input_map_position = input_map_position)

            i_block = 0

            for j_weight_load in range(self.weight_update_times_per_inst):
                self.wu_ls_bank(num_ls = self.weight_update_ls[j_weight_load], 
                        num_channel = config.PC,  # !!!可能有很多channel浪费
                        i_block = i_block)
                
                for i in range (acc0.CIMsWriteWidth//acc0.BusWidth*config.WEIGHT_ROW):
                    self.idle()

                for i_input_channel in range(i_IS_load * self.input_channels_per_ISload, 
                                            i_IS_load * self.input_channels_per_ISload + 
                                            self.IS_load_rows[i_IS_load] // self.rows_per_input_channel): # 选中一个input channel
                    for j_ls in range(self.weight_update_ls[j_weight_load]): #选中一个ls
                        j_compute_block = i_block + j_ls
                        self.compute(i_input_channel = i_input_channel, 
                            computing_block = j_compute_block)

                i_block += self.weight_update_ls[j_weight_load]

    def ws_process(self):
        # Processing logic for WS
        config = self.config
        i_block = 0
        self.load_is_block(num_rows = self.rows_per_input_channel * self.input_channels_per_ISload, input_map_position = 0)
        for i_weight_update in range(self.weight_update_times_per_inst):
            self.wu_ls_bank(num_ls = self.weight_update_ls[i_weight_update], 
                        num_channel = config.PC,  # !!!可能有很多channel浪费
                        i_block = i_block)
            for i in range (self.acc0.CIMsWriteWidth//self.acc0.BusWidth*config.WEIGHT_ROW):
                self.idle()
            
            for i_input_channel in range(self.input_map_channel):
                for j_ls in range(self.weight_update_ls[i_weight_update]): #选中一个ls
                    j_compute_block = i_block + j_ls
                    self.compute(i_input_channel = i_input_channel, 
                            computing_block = j_compute_block)

            i_block += self.weight_update_ls[i_weight_update]

    def compile(self):
        # Main method to compile instructions
        print("**"+self.data_stream+" compiling**")
        self.log_init()
        if self.data_stream in ['isap', 'ispp']:
            self.is_process()
        elif self.data_stream in ['wsap', 'wspp']:
            self.ws_process()
        # Additional logic to finalize compilation and manage stack
        for i in range(self.fifo_len):
            self.stk.push()
        

    # Add any additional methods or utility functions as needed
    def print(self):
        print("System config:")
        for attr, value in self.config.__dict__.items():
            print(f"{attr} = {value}")

        print("\nHardware config:")
        for attr, value in self.acc0.__dict__.items():
            print(f"{attr} = {value}")

        print("\nInput map mapping:")
        print(f"input_data_per_row = {self.input_data_per_row}")
        print(f"rows_per_input_channel = {self.rows_per_input_channel}")
        print(f"input_channels_per_ISload = {self.input_channels_per_ISload}")
        print(f"IS_load_times_per_inst = {self.IS_load_times_per_inst}")
            
        print(f"IS_load_rows = {self.IS_load_rows}")

        print("\nWeight map mapping:")
        print(f"weight_block_row = {self.weight_block_row}")
        print(f"weight_block_col = {self.weight_block_col}")
        print(f"weight_block_num = {self.weight_block_num}")
        print(f"weight_update_times_per_inst = {self.weight_update_times_per_inst}")
                
        print(f"weight_update_ls = {self.weight_update_ls}")
                
        print("ls_matrix:\n", self.ls_matrix, "\n")
        print("atos_matrix:\n", self.atos_matrix, "\n")


# Example usage:
if __name__ == "__main__":
    config = Config(al=128, pc=16, scr=4, bus_width=128, is_depth=512, os_depth=1024)
    gli = ['mvm', (32, 512, 512)]
    data_stream = 'wspp'
    VERIFY = False

    compiler = MicroInstructionCompiler(config, gli, data_stream, VERIFY)
    compiler.compile()
    compiler.print()

    # Additional code to output or work with the compiled instructions

