### dolist

* AHB总线带宽-标准值256b，AHB半双工，AXI全双工
  * brust传输？模型假设标准，考据，需不需要考虑握手信号
  * AXI Stream



### MVM.ISA功耗建模

* Lin	<pos>	<is-addr>  

* Linp	<pos>  

* Lwt	<pos>	<cm-addr>

* Lwtp	<pos>

* Cmpfis	<is-addr>	<ca>	<atos>
	* Cmpfis	<is-addr>	<ca>	<aor>	
	* Cmpfis	<is-addr>	<ca>	<tos>	<os-addr>
	* Cmpfis	<is-addr>	<ca>	<aos>	<os-addr>
	* Cmpfis	<is-addr>	<ca>	<ptos>	
	* Cmpfis	<is-addr>	<ca>	<paos> 

* Cmpfgt	<pos>	<ca>	<atos>
	* Cmpfgt	<pos>	<ca>	<aor>
	* Cmpfgt	<pos>	<ca>	<tos>	<os-addr>
	* Cmpfgt	<pos>	<ca>	<aos>	<os-addr>
	* Cmpfgt	<pos>	<ca>	<ptos>  
	* Cmpfgt	<pos>	<ca>	<paos>  

* Cmpfgtp	<pos>

* Lpenalty	

* Nop
* Nop	<aor>	 <os-addr>




### ==Single==-Instruction Power Breakdown

*P_==si== = f( is_size, acc_len, scr, para_channel, os_size )*

*internal_bandwidth = g( is_size, acc_len, scr, para_channel, os_size )*

Golden Case: 

[Data Pattern, 50% input toggle]

#### fd

* input_sram: *Power = f( is_width, is_depth)* <Sram Power function pJpb>
* fd.regs: *(Power = P(Golden Case) / BW(Golden Case) )x BW* 

#### macros

* cims: *acc_len,para_c --> num of cims*   *P = f(scr) ? (zyr)*
* cm.regs: tong shang

#### gd

* output_sram: tong shang
* gd.regs: tong shang

#### top.regs: tong shang 







### 关于包含DRAM仿真的系统simulator

* 假设足够大的L2容量，不考虑L2和DDR间的重复调度，评估一个P(DRAM)和P(L1)\P(L2)的相对大小，如果差距巨大？怎办。



### Project Schedule

* 固定硬件搭建、固定数据流编译，想清楚完整数据流、添加额外指令到top // w1

* 出每个指令的性能 <定时钟频率，CIM Macro的Access Time> | 写其他数据流的mi_compiler // w1~w2
* 得到固定硬件的多数据流评估 <包括Attention计算> | *修改硬件参数对应的RTL代码，如何正确评估功耗模型？reg功耗大* // w3
* 整体评估，包括硬件参数的评估 // w4



### OS overflow Penalty（）

* tos / aos操作，若指令中os的索取地址 $addr > os_depth，则
    * tos 指令：变成aor指令 ? ，penalty_fg = `enable（penalty fg从指令中拉出来，硬件时序问题，代码再规整一遍）
    * aos指令：变成一周期penalty_load? + 原计算的aor指令 ac_fg=1?，penalty_fg = `enable

* tos / aos操作，在每次到达图的最终边界时（对于每个input vector），os_depth += 1，产生一个os读请求（wt $0）



aos操作，若os已经溢出，aos编译为pload + paos

若os未溢出，且当前block是weight map列方向的最后一个block，aos编译为paos，os虚拟容量加一，此时仍然需要相应os地址的读请求（由于前面没有pload指令，adder source还是oob <s6指示的>）

否则，即os未溢出，当前block不是最后一个block的aos，正常产生对应os地址的request



tos操作，若os已经溢出，tos编译为ptos

若os未溢出，且当前block是列向的最后一个block，tos编译为ptos，os虚拟容量加一

否则，即os未溢出，当前block不是最后，正常tos



aor操作





### 关于VLIW

在传统多级流水线处理器向着高性能处理器演进中，个人通俗的理解，面临的基本问题是硬件增加，执行的软件不变，如何在一周期能执行多指令？

其中一条技术路径是超长指令字，即将多个独立的指令捆绑，并行送入多个硬件；这样做的好处是简化硬件设计，硬件无条件信任软件（编译器）对于指令依赖的处理；

另一条技术路径是超标量处理器，硬件决策，多发射，乱序执行；

VLIW由于复杂的编译器优化（不同硬件不适配）没有在通用计算领域取得应用，但在DSP中得到广泛应用。

![image-20231224213423835](image-20231224213423835.png)



我们要做的其实不是VLIW，我们并不是在讨论指令级并行的问题，而是数据级并行，一种类似于SIMD的简单流水线架构






### din带宽

![f34e1e06f14cefb0a297b0fbdd0b9c8](f34e1e06f14cefb0a297b0fbdd0b9c8.png)



## ISA

​		[cmp, gt, pause]

* load IS
  * lisp [0, 0, 1]  fill reg0
  * lis [0, 0, 0]
* weight update
  * wup [0, 1, 1]  fill reg1
  * wu [0, 1, 0]  
* compute from IS
  * cmpfis [1, 0, 0]  
* compute from go-through
  * cmpgtp [1, 1, 1]  fill reg0
  * cmpgt [1, 1, 0]  

​		FD NOP: [1, 0, 1]

* load OR / fusion / sfus





