def verify(inst, new_addr):
    if inst.find("tos") == -1 and inst.find("aos") == -1: # no tos/aos
        return True

    # elif inst.find("paos") != -1 or inst.find("ptos") != -1: # paos or ptos
    #     return False
    
    elif inst.find("paos") == -1 or inst.find("ptos") == -1: # paos or ptos
        return True

    else: # tos or aos 
        os_addr = int(inst[inst.find("<os_addr_wt>")+13 : len(inst)])
        if (os_addr + new_addr) % 2 == 1: #even and odd
            return True
        else:
            return False

class inst_stack:
    def __init__(self, len = 8):
        self.len = len
        self.inst_fifo = ['\n' for i in range(len)]
        self.req_quene = [0 for i in range(len)]
        self.addr_quene = [0 for i in range(len)]
        self.preq_quene = [0 for i in range(len)]
        self.paddr_quene = [0 for i in range(len)]

    def push(self, inst = '\n', rd_req = 0, rd_addr = 0):
        if rd_req == 1: # new rd request
            for i in reversed(range(self.len)):
                if self.req_quene[i] == 0 and verify(self.inst_fifo[i], rd_addr) == True:
                    self.req_quene[i] = 1
                    self.addr_quene[i] = rd_addr
                    rd_req = 0 #Read Request Solved
                    break
                else:
                    if i == 0: #Read Request Unsolved
                        print("@@@@@@@@@@@@@@@@@@@@@!Warning! Unsolved Read Request!!@@@@@@@@@@@@@@@@@@@@@")

        with open("mi.log","a") as f:
            if self.inst_fifo[0] != "\n":
                if self.preq_quene[0] == 1:
                    f.write("nop\t <os_addr_rd> "+str(self.paddr_quene[0])+'\n')
                if self.req_quene[0] == 0:
                    f.write(str(self.inst_fifo[0]))
                elif self.req_quene[0] == 1:
                    f.write(str(self.inst_fifo[0][0:len(self.inst_fifo[0])-1]) + "\t <os_addr_rd> "+str(self.addr_quene[0])+'\n')
            
        # print(self.inst_fifo[0])

        for i in range(self.len):
            if i != self.len-1:
                self.inst_fifo[i] = self.inst_fifo[i+1]
                self.req_quene[i] = self.req_quene[i+1]
                self.addr_quene[i] = self.addr_quene[i+1]
                self.preq_quene[i] = self.preq_quene[i+1]
                self.paddr_quene[i] = self.paddr_quene[i+1]
            else:
                self.inst_fifo[i] = inst
                # self.req_quene[i] = rd_req
                self.req_quene[i] = 0
                self.addr_quene[i] = rd_addr
                self.preq_quene[i] = rd_req
                self.paddr_quene[i] = rd_addr

    def check(self):
        print("inst:\n\t", self.inst_fifo)
        print(self.req_quene,'\n',self.addr_quene)




'''
s0 = inst_stack(8)
s0.push(inst="lis <is_addr> 0\n",rd_req=0,rd_addr=252)
s0.push(inst="cmpfis	 <is_addr> 8	 <ca> 3	 <tos>	 <os_addr> 252\n",rd_req=0,rd_addr=251)
s0.push(inst="cmpfis	 <is_addr> 11	 <ca> 0	 <aos>	 <os_addr> 253\n",rd_req=1,rd_addr=253)
s0.push(inst="cmpfis	 <is_addr> 9	 <ca> 1	 <tos>	 <os_addr> 255\n",rd_req=0,rd_addr=251)
s0.push(inst="cmpfis	 <is_addr> 10	 <ca> 2	 <tos>	 <os_addr> 255\n",rd_req=0,rd_addr=251)
s0.push(inst="cmpfis	 <is_addr> 11	 <ca> 3	 <aos>	 <os_addr> 255\n",rd_req=1,rd_addr=255)
for i in range(8):
    s0.push()
'''


