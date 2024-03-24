#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <string.h>
#include "hw_config.h"
#include "inst_stack.h"
#include "instruction_count.h"

int bus_width, al, pc, scr, is_depth, os_depth, freq;
char* operation;
int dim1, dim2, dim3;
char* data_stream;

hwc acc0;
Config config;
InstructionCount instructionCount;

int weight_map_channel, weight_map_length;
int input_map_length, input_map_channel;

int weight_block_col, weight_block_row, weight_block_num, weight_update_times_per_inst;
int input_data_per_row, rows_per_input_channel, input_channels_per_ISload, IS_load_times_per_inst;
int para_times, acc_times;
int is_addr_record = 114514; //随便给了个不可能的初值

int gt_in_map_record;
int os_virtual_depth;

int* IS_load_rows;
int* weight_update_ls;

int** ls_matrix;
int** atos_matrix;

void idle(){
    instructionCount.Nop++; 
}

int load_is_block(int num_rows, int input_map_position) {
    for (int i_rows = 0; i_rows < num_rows; ++i_rows) {
        input_map_position += (config.BUS_WIDTH / config.DATA_WIDTH) * (acc0.InputSRAMWidth / acc0.BusWidth - 1);
        for (int j_reg = acc0.InputSRAMWidth / acc0.BusWidth - 1; j_reg >= 0; --j_reg) {
            if (j_reg != 0) {
                instructionCount.Linp++;
            } else {
                instructionCount.Lin++;
            }
            input_map_position -= (config.BUS_WIDTH / config.DATA_WIDTH);
            // 注意: 每个channel的最后一行可能需要特殊处理
        }
        input_map_position += (acc0.InputSRAMWidth / config.DATA_WIDTH) + (config.BUS_WIDTH / config.DATA_WIDTH);
    }
    return input_map_position;
}

int wu_ls_bank(int num_ls, int num_channel, int i_block) {
    for (int i_ls = 0; i_ls < num_ls; ++i_ls) {
        int i_pt, i_at;
        if (strcmp(data_stream, "isap") == 0 || strcmp(data_stream, "wsap") == 0) {
            i_pt = i_block / weight_block_col;
            i_at = i_block % weight_block_col;
        } else if (strcmp(data_stream, "ispp") == 0 || strcmp(data_stream, "wspp") == 0) {
            i_pt = i_block % weight_block_row;
            i_at = i_block / weight_block_row;
        }

        for (int j_channel = 0; j_channel < num_channel; j_channel++) {
            int i_weight_channel = i_pt * config.PC + j_channel;
            int j_data_in_channel = i_at * config.AL;
            int weight_map_position = i_weight_channel * weight_map_length + j_data_in_channel;
            
            for (int k_reg = acc0.CIMsWriteWidth / acc0.BusWidth * config.WEIGHT_ROW - 1; k_reg >= 0; k_reg--) {
                weight_map_position = i_weight_channel * weight_map_length + j_data_in_channel + k_reg * acc0.BusWidth / config.DATA_WIDTH;
                int row_reg = (acc0.CIMsWriteWidth / acc0.BusWidth * config.WEIGHT_ROW - 1 - k_reg) / (acc0.CIMsWriteWidth / acc0.BusWidth);
                int pause_reg = k_reg % (acc0.CIMsWriteWidth / acc0.BusWidth);

                if (pause_reg == 0) {
                    instructionCount.Lwt++;
                } else {
                    instructionCount.Lwtp++;
                }
            }
        }
        i_block += 1;
    }
    return i_block;
}

void compute(int i_input_channel, int computing_block) {
    int i_ls = computing_block % config.SCR;
    int i_pt, i_at, is_addr, os_addr, input_map_position, j_reg;
    
    if (strcmp(data_stream, "isap") == 0 || strcmp(data_stream, "wsap") == 0) {
        i_pt = computing_block / weight_block_col;
        i_at = computing_block % weight_block_col;
    } else if (strcmp(data_stream, "ispp") == 0 || strcmp(data_stream, "wspp") == 0) {
        i_pt = computing_block % weight_block_row;
        i_at = computing_block / weight_block_row;
    }
    
    int atos_flag = atos_matrix[i_pt][i_at];
    // printf("i_pt= %d\n",i_pt);
    // printf("i_at= %d\n",i_at);
    // printf("atos_flag= %d\n",atos_flag);
    os_addr = i_input_channel * para_times + i_pt;

    if (strcmp(data_stream, "isap") == 0 || strcmp(data_stream, "ispp") == 0) {
        is_addr = (i_input_channel % input_channels_per_ISload) * rows_per_input_channel + i_at;
    } else if (strcmp(data_stream, "wsap") == 0 || strcmp(data_stream, "wspp") == 0) {
        is_addr = i_input_channel * rows_per_input_channel + i_at;
    }

    if ((strcmp(data_stream, "wsap") == 0 || strcmp(data_stream, "wspp") == 0) && (i_input_channel >= input_channels_per_ISload)) {
        input_map_position = i_input_channel * input_map_length + i_at * config.AL + (config.BUS_WIDTH / config.DATA_WIDTH) * (acc0.InputSRAMWidth / acc0.BusWidth - 1);
        
        if (is_addr == is_addr_record) instructionCount.IS_reward++;
            is_addr_record = is_addr;

        for (j_reg = acc0.InputSRAMWidth / acc0.BusWidth - 1; j_reg >= 0; j_reg--) {
            
            if ((gt_in_map_record / (acc0.InputSRAMWidth / config.DATA_WIDTH)) == (input_map_position / (acc0.InputSRAMWidth / config.DATA_WIDTH)) && j_reg != 0) {
                input_map_position -= config.BUS_WIDTH / config.DATA_WIDTH;
                continue;
            }

            if (j_reg != 0) {   // Cmpfgtp
                instructionCount.Cmpfgtp++;
                input_map_position -= config.BUS_WIDTH / config.DATA_WIDTH;
            } else {            // Cmpfgt
                if (atos_flag == 2) {
                    if (os_addr > os_virtual_depth) { // aos, os overflow
                        if (i_at == acc_times - 1) {
                            os_virtual_depth += 1;
                        }
                        instructionCount.Cmpfgt_paos++;
                        instructionCount.Lpenalty+=acc0.OutputSRAMWidth / (config.RESULT_WIDTH / config.DATA_WIDTH) / config.BUS_WIDTH;
                    } else { // aos, os not overflow
                        if (i_at == acc_times - 1) {
                            os_virtual_depth += 1;
                            instructionCount.Cmpfgt_paos++;
                        }
                        else instructionCount.Cmpfgt_aos++;
                        instructionCount.Nop_w_rd++;
                    }
                    // Additional conditions and corresponding fprintf statements should be added here as per the Python logic
                }
                
                if (atos_flag == 1){
                    if (os_addr > os_virtual_depth){    // tos, os overflow
                        if (i_at == acc_times-1)    // complete one output, gen rd request, aos: paos(go through)
                            os_virtual_depth += 1;
                        instructionCount.Cmpfgt_ptos++;
                    }
                    else{    // tos, os not overflow
                        if (i_at == acc_times-1){ //gen rd request
                            os_virtual_depth += 1;
                            instructionCount.Cmpfgt_ptos++;
                        }
                        else{
                            instructionCount.Cmpfgt_tos++;
                        }
                    }
                }

                if (atos_flag == 0){
                    instructionCount.Cmpfgt_aor++;
                }
            }
        }
        gt_in_map_record = input_map_position;
    }

    else{
        if (is_addr == is_addr_record) instructionCount.IS_reward++;
            is_addr_record = is_addr;

        if (atos_flag == 2) { //aos
            if (os_addr > os_virtual_depth) {   // aos, os overflow
                if (i_at == acc_times-1) {
                    os_virtual_depth += 1;
                }
                instructionCount.Cmpfis_paos++;
                instructionCount.Lpenalty+=acc0.OutputSRAMWidth / (config.RESULT_WIDTH / config.DATA_WIDTH) / config.BUS_WIDTH;
            } else {                             // aos, os not overflow
                if (i_at == acc_times - 1) {
                    os_virtual_depth += 1;
                    instructionCount.Cmpfis_paos++;
                }
                else instructionCount.Cmpfis_aos++;
                instructionCount.Nop_w_rd++;
            }
        }

        if (atos_flag == 1){
            if (os_addr > os_virtual_depth){    // tos, os overflow
                if (i_at == acc_times-1)    // complete one output, gen rd request, aos: paos(go through)
                    os_virtual_depth += 1;
                instructionCount.Cmpfis_ptos++;
            }
            else{    // tos, os not overflow
                if (i_at == acc_times-1){ //gen rd request
                    os_virtual_depth += 1;
                    instructionCount.Cmpfis_ptos++;
                }
                else{
                    instructionCount.Cmpfis_tos++;
                }
            }
        }

        if (atos_flag == 0){
            instructionCount.Cmpfis_aor++;
        }
    }
}

void is_process(void) {
    int input_map_position = 0;
    int i_block = 0;

    for (int i_IS_load = 0; i_IS_load < IS_load_times_per_inst; i_IS_load++) {
        input_map_position = load_is_block(IS_load_rows[i_IS_load], input_map_position);

        i_block = 0;
        for (int j_weight_load = 0; j_weight_load < weight_update_times_per_inst; j_weight_load++) {
            //i_block = 
            wu_ls_bank(weight_update_ls[j_weight_load], config.PC, i_block);

            for (int i = 0; i < acc0.CIMsWriteWidth / acc0.BusWidth * config.WEIGHT_ROW; i++) {
                idle();
            }

            for (int i_input_channel = i_IS_load * input_channels_per_ISload; 
                 i_input_channel < i_IS_load * input_channels_per_ISload + 
                 IS_load_rows[i_IS_load] / rows_per_input_channel; 
                 i_input_channel++) {

                for (int j_ls = 0; j_ls < weight_update_ls[j_weight_load]; j_ls++) {
                    int j_compute_block = i_block + j_ls;
                    compute(i_input_channel, j_compute_block);
                }
            }

            i_block += weight_update_ls[j_weight_load];
        }
    }
}

void ws_process(void) {
    int i_block = 0;

    // 假设rows_per_input_channel和input_channels_per_ISload已经定义
    load_is_block(rows_per_input_channel * input_channels_per_ISload, 0);

    for (int i_weight_update = 0; i_weight_update < weight_update_times_per_inst; i_weight_update++) {
        wu_ls_bank(weight_update_ls[i_weight_update], config.PC, i_block);

        for (int i = 0; i < acc0.CIMsWriteWidth / acc0.BusWidth * config.WEIGHT_ROW; i++) {
            idle();
        }

        for (int i_input_channel = 0; i_input_channel < input_map_channel; i_input_channel++) {
            for (int j_ls = 0; j_ls < weight_update_ls[i_weight_update]; j_ls++) {
                int j_compute_block = i_block + j_ls;
                compute(i_input_channel, j_compute_block);
            }
        }

        i_block += weight_update_ls[i_weight_update];
    }
}

void mvm_process(int dim1, int dim2, int dim3){ //实际上的输入参数是input和weight map的长宽
    weight_map_channel = dim1;
    weight_map_length = dim2;

    input_map_length = dim2;
    input_map_channel = dim3;

    input_data_per_row = floor(acc0.InputSRAMWidth / config.DATA_WIDTH);
    rows_per_input_channel = (int)ceil((float)input_map_length / input_data_per_row);
    input_channels_per_ISload = acc0.InputSRAMDepth / rows_per_input_channel;
    if (input_channels_per_ISload > input_map_channel)
        input_channels_per_ISload = input_map_channel;
    IS_load_times_per_inst = (int)ceil((float)input_map_channel / input_channels_per_ISload);

    IS_load_rows = (int*)malloc(IS_load_times_per_inst * sizeof(int));
    for (int i = 0; i < IS_load_times_per_inst; ++i) {
        IS_load_rows[i] = input_channels_per_ISload * rows_per_input_channel;
    }
    if (input_map_channel % input_channels_per_ISload != 0) {
        IS_load_rows[IS_load_times_per_inst - 1] = (input_map_channel % input_channels_per_ISload) * rows_per_input_channel;
    }

    weight_block_row = (int)ceil((float)weight_map_channel / config.PC);
    weight_block_col = (int)ceil((float)weight_map_length / config.AL);
    weight_block_num = weight_block_col * weight_block_row;
    weight_update_times_per_inst = (int)ceil((float)weight_block_num / config.SCR);

    weight_update_ls = (int*)malloc(weight_update_times_per_inst * sizeof(int));
    for (int i = 0; i < weight_update_times_per_inst; ++i) {
        weight_update_ls[i] = config.SCR;
    }
    if (weight_block_num % config.SCR != 0) {
        weight_update_ls[weight_update_times_per_inst - 1] = weight_block_num % config.SCR;
    }

    para_times = weight_block_row;
    acc_times = weight_block_col;

    weight_map_channel = para_times * config.PC;
    weight_map_length = acc_times * config.AL;

    input_map_length  = acc_times * config.AL;
    input_map_channel  = input_map_channel;

    // 分配ls_matrix并初始化为0
    ls_matrix = (int**)malloc(para_times * sizeof(int*));
    for(int i = 0; i < para_times; ++i) {
        ls_matrix[i] = (int*)malloc(acc_times * sizeof(int));
        for(int j = 0; j < acc_times; ++j) {
            ls_matrix[i][j] = 0;
        }
    }

    // 分配atos_matrix并初始化为0
    atos_matrix = (int**)malloc(para_times * sizeof(int*));
    for(int i = 0; i < para_times; ++i) {
        atos_matrix[i] = (int*)malloc(acc_times * sizeof(int));
        for(int j = 0; j < acc_times; ++j) {
            atos_matrix[i][j] = 0;
        }
    }

    int ls_fg = 0;

    if (strcmp(data_stream, "isap") == 0 || strcmp(data_stream, "wsap") == 0) {
        // ap 优先acc
        for (int i_pt = 0; i_pt < para_times; ++i_pt) {
            for (int i_at = 0; i_at < acc_times; ++i_at) {
                ls_matrix[i_pt][i_at] = ls_fg;
                ls_fg = (ls_fg + 1) % config.SCR;
            }
        }
        
        for (int i_pt = 0; i_pt < para_times; ++i_pt) {
            int row_st_fg = 0; // row start flag
            for (int i_at = 0; i_at < acc_times; ++i_at) {    
                if (i_at == acc_times-1 || ls_matrix[i_pt][i_at] == acc0.LocalSwitchrows - 1) {
                    atos_matrix[i_pt][i_at] = row_st_fg == 0 ? 1 : 2; // 1 for TOS, 2 for AOS
                    row_st_fg = 1;
                }
            }
        }
    } else if (strcmp(data_stream, "ispp") == 0 || strcmp(data_stream, "wspp") == 0) {
        // pp 优先para
        for (int i_at = 0; i_at < acc_times; ++i_at) {
            for (int i_pt = 0; i_pt < para_times; ++i_pt) {
                ls_matrix[i_pt][i_at] = ls_fg;
                ls_fg = (ls_fg + 1) % config.SCR;
            }
        }

        for (int i_pt = 0; i_pt < para_times; ++i_pt) {
            for (int i_at = 0; i_at < acc_times; ++i_at) {    
                atos_matrix[i_pt][i_at] = i_at == 0 ? 1 : 2; // 1 for TOS, 2 for AOS
            }
        }
    }

    // // 打印基本计算结果
    // printf("input_data_per_row = %d\n", input_data_per_row);
    // printf("rows_per_input_channel = %d\n", rows_per_input_channel);
    // printf("input_channels_per_ISload = %d\n", input_channels_per_ISload);
    // printf("IS_load_times_per_inst = %d\n", IS_load_times_per_inst);

    // // 打印IS_load_rows数组
    // printf("IS_load_rows:\n");
    // for (int i = 0; i < IS_load_times_per_inst; ++i) {
    //     printf("%d ", IS_load_rows[i]);
    // }
    // printf("\n");

    // // 打印权重更新信息
    // printf("weight_block_row = %d\n", weight_block_row);
    // printf("weight_block_col = %d\n", weight_block_col);
    // printf("weight_block_num = %d\n", weight_block_num);
    // printf("weight_update_times_per_inst = %d\n", weight_update_times_per_inst);

    // // 打印weight_update_ls数组
    // printf("weight_update_ls:\n");
    // for (int i = 0; i < weight_update_times_per_inst; ++i) {
    //     printf("%d ", weight_update_ls[i]);
    // }
    // printf("\n");

    // // 打印ls_matrix
    // printf("ls_matrix:\n");
    // for (int i = 0; i < para_times; ++i) {
    //     for (int j = 0; j < acc_times; ++j) {
    //         printf("%d ", ls_matrix[i][j]);
    //     }
    //     printf("\n");
    // }

    // // 打印atos_matrix
    // printf("atos_matrix:\n");
    // for (int i = 0; i < para_times; ++i) {
    //     for (int j = 0; j < acc_times; ++j) {
    //         printf("%d ", atos_matrix[i][j]);
    //     }
    //     printf("\n");
    // }


    gt_in_map_record = 0;
    os_virtual_depth = acc0.OutputSRAMDepth;

    if (strcmp(data_stream, "ispp") == 0 || strcmp(data_stream, "isap") == 0){
        is_process();
    }
    else
        ws_process();

}

void ph2_process(void){
    strcpy(data_stream, "ispp");
    for(int i=0; i<dim3; i++){
        mvm_process(dim1,dim2/config.PIPELINE_STAGES,dim1);
        mvm_process(dim2/config.PIPELINE_STAGES,dim1,dim1);
    }
}

void lhd_process(void){
    int K_map_channel = dim1;
    int K_map_length = dim2 / dim3;
    int K_para_times = ceil((float)K_map_channel / config.PC);
    int K_acc_times = ceil((float)K_map_length / config.AL);
    int K_map_block = K_para_times * K_acc_times;
    int Sqk = K_map_block;

    int V_map_channel = dim2 / dim3;
    int V_map_length = dim1;
    int V_para_times = ceil((float)V_map_channel / config.PC);
    int V_acc_times = ceil((float)V_map_length / config.AL);
    int V_map_block = V_para_times * V_acc_times;
    int Spv = V_map_block;

    int using_scr = K_map_block + V_map_block;

    if (using_scr > config.SCR){
        printf("ERROR\n");
        return;
    }

    int Q_serial_times = (Sqk + config.PIPELINE_STAGES) / Sqk + 1;

    // we are using wspp here
    para_times = using_scr;
    acc_times = 1;

    // 分配ls_matrix
    int ls_fg = 0;
    ls_matrix = (int**)malloc(para_times * sizeof(int*));
    for(int i = 0; i < para_times; ++i) {
        ls_matrix[i] = (int*)malloc(acc_times * sizeof(int));
        for(int j = 0; j < acc_times; ++j) {
            ls_matrix[i][j] = ls_fg;
        }
    }

    // 分配atos_matrix
    atos_matrix = (int**)malloc(para_times * sizeof(int*));
    for(int i = 0; i < para_times; ++i) {
        atos_matrix[i] = (int*)malloc(acc_times * sizeof(int));
        for(int j = 0; j < acc_times; ++j) {
            atos_matrix[i][j] = 0;
        }
    }

    int i_block = 0;
    for(int i = 0; i < K_para_times; i++){
        for (int j = 0; i < K_acc_times; j++){
            if (j == K_acc_times - 1)
                atos_matrix[i_block][0] = 1;
            else 
                atos_matrix[i_block][0] = 0;
            i_block+=1;
        }
    }

    for(int i = 0; i < V_para_times; i++){
        for (int j = 0; i < V_acc_times; j++){
            if (j == V_acc_times - 1)
                atos_matrix[i_block][0] = 1;
            else 
                atos_matrix[i_block][0] = 0;
            i_block+=1;
        }
    }

    for(int i_head=0; i_head<dim3; i_head++){
        // 我们不用更新IS，which is great
        // 首先更新K和V矩阵到CIM中
        wu_ls_bank(para_times, config.PC, 0);
        for (int i = 0; i < acc0.CIMsWriteWidth / acc0.BusWidth * config.WEIGHT_ROW; i++) {
            idle();
        }
        for (int j = 0; j < dim1 / Sqk; j++){
            for (int k = 0; k < Q_serial_times; k++){
                for(int m_count=0; m_count<Sqk; m_count++){
                    compute(j * Sqk + k, m_count);
                }
            }
            for (int k = 0; k < Q_serial_times; k++){
                for(int m_count=0; m_count<Spv; m_count++){
                    //compute(?, m_count);
                }
            }
        }

    }
}

void mha_process(void){
    if (strcmp(data_stream, "ph2") == 0){
        ph2_process();
    }
    else if (strcmp(data_stream, "lhd") == 0)
        lhd_process();
}

int main(int argc, char *argv[]){
    if (argc != 13) {
        printf("error!");
        return 1;
    }

    // printf("Number of command line arguments: %d\n", argc);

    bus_width = atoi(argv[1]);
    al = atoi(argv[2]);
    pc = atoi(argv[3]);
    scr = atoi(argv[4]);
    is_depth = atoi(argv[5]);
    os_depth = atoi(argv[6]);
    freq = atoi(argv[7]);

    operation = argv[8];

    dim1 = atoi(argv[9]);
    dim2 = atoi(argv[10]);
    dim3 = atoi(argv[11]); 

    data_stream = argv[12];

    InitConfig(&config, bus_width, al, pc, scr, is_depth, os_depth, freq);
    // PrintConfig(&config);

    Inithwc(&acc0, config);
    // Printhwc(&acc0);

    if (strcmp(operation, "mvm") == 0)
        mvm_process(dim1,dim2,dim3);
    else if (strcmp(operation, "mha") == 0)
            mha_process();
        

    // #region output
    //***************************************** terminal output ****************************************
    printInstructionCount(&instructionCount);

    printf("%s", data_stream);

    //******************************************* csv output *******************************************
    // 检查文件是否存在
    FILE *file = fopen("count.csv", "r");
    int needHeader = 0;
    if (file == NULL) {
        needHeader = 1; // 文件不存在，需要写入表头
    } else {
        fclose(file); // 文件已存在，关闭文件
    }

    // 以追加模式打开文件，如果不存在则创建
    file = fopen("count.csv", "a");
    if (file == NULL) {
        perror("Failed to open file");
        return EXIT_FAILURE;
    }

    // 如果需要，写入表头
    if (needHeader) {
        fprintf(file, "bus_width,al,pc,scr,is_depth,os_depth,freq,operation,dim1,dim2,dim3,data_stream,");
        fprintf(file, "Lin,Linp,Lwt,Lwtp,Cmpfis_aor,Cmpfis_tos,Cmpfis_aos,Cmpfis_ptos,Cmpfis_paos,");
        fprintf(file, "Cmpfgt_aor,Cmpfgt_tos,Cmpfgt_aos,Cmpfgt_ptos,Cmpfgt_paos,Cmpfgtp,Lpenalty,Nop,Nop_w_rd,");
        fprintf(file, "IS_reward,L2_reward,Fussion\n");
    }

    // 写入命令行参数到文件
    fprintf(file, "%d,%d,%d,%d,%d,%d,%d,%s,%d,%d,%d,%s,",
            bus_width, al, pc, scr, is_depth, os_depth, freq, operation,
            atoi(argv[9]), atoi(argv[10]), atoi(argv[11]), argv[12]);

    // 写入InstructionCount到文件
    fprintf(file, "%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d\n",
            instructionCount.Lin, instructionCount.Linp, instructionCount.Lwt, instructionCount.Lwtp,
            instructionCount.Cmpfis_aor, instructionCount.Cmpfis_tos, instructionCount.Cmpfis_aos,
            instructionCount.Cmpfis_ptos, instructionCount.Cmpfis_paos,
            instructionCount.Cmpfgt_aor, instructionCount.Cmpfgt_tos, instructionCount.Cmpfgt_aos,
            instructionCount.Cmpfgt_ptos, instructionCount.Cmpfgt_paos,
            instructionCount.Cmpfgtp, instructionCount.Lpenalty, instructionCount.Nop, instructionCount.Nop_w_rd, 
            instructionCount.IS_reward,instructionCount.L2_reward,instructionCount.Fussion);

    // 关闭文件
    fclose(file);


    // //*******************************************清理*******************************************
    for(int i = 0; i < para_times; ++i) {
        free(ls_matrix[i]);
        free(atos_matrix[i]);
    }
    free(ls_matrix);
    free(atos_matrix);
    free(weight_update_ls);
    free(IS_load_rows);

    return 0;
}

/*
来起名
gli:
    "mha", seq_len, hid_size, head_num

    hid_size = head_num * embedding_length

    e.g.    "mha", N, 768, 12

data stream:    
    1. 2ph(two phase)
        分为QK/PV两个phase的计算，将QK和PV看成两个独立的矩阵乘操作
    2. lhd(Low-Hierarchy-Dive)
        每次只送入一个q向量，得到一个xo，
*/
