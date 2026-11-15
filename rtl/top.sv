// top.sv: array + control logic + ABFT checker
//
// DATAFLOW selects the array: 0 = weight-stationary, 1 = output-stationary. Both controls have
// the same ports, so the checker is the same for both.
//
// The checker takes its own copy of A and B at the edge where the control accepts start, and
// reads the result when done is high. The array itself is not changed by the checker.
//
// Simulation only: inj_add is added to c_mat (mod 2^W, per element) between the array and
// everything that reads the result, so a testbench can put a wrong value into C. It is a
// plain variable that a testbench writes; it is removed from synthesis and is zero by default.

module top #(
    parameter int N        = 4,
    parameter int W        = 18,
    parameter int DATAFLOW = 0
) (
    input  logic                  clk,
    input  logic                  rst_n,
    input  logic                  stall,
    input  logic                  start,
    input  logic                  keep_w,    // weight-stationary only: reuse the loaded B
    input  logic [N*N-1:0][7:0]   a_mat,
    input  logic [N*N-1:0][7:0]   b_mat,

    output logic                  busy,
    output logic                  done,
    output logic [N*N-1:0][W-1:0] c_mat,

    output logic                  chk_valid,
    output logic                  err_flag,
    output logic                  err_loc_valid,
    output logic [$clog2(N)-1:0]  err_row,
    output logic [$clog2(N)-1:0]  err_col
);

    logic [N*N-1:0][W-1:0] c_core;
    logic                  accept, keep_eff;

    assign accept   = !busy && start && !stall;
    assign keep_eff = (DATAFLOW == 0) ? keep_w : 1'b0;

    if (DATAFLOW == 0) begin : g_ws
        systolic_ws_ctrl #(.N(N), .W(W)) u_ctrl (
            .clk(clk), .rst_n(rst_n), .stall(stall), .start(start), .keep_w(keep_w),
            .a_mat(a_mat), .b_mat(b_mat), .busy(busy), .done(done), .c_mat(c_core));
    end else begin : g_os
        systolic_os_ctrl #(.N(N), .W(W)) u_ctrl (
            .clk(clk), .rst_n(rst_n), .stall(stall), .start(start), .keep_w(keep_w),
            .a_mat(a_mat), .b_mat(b_mat), .busy(busy), .done(done), .c_mat(c_core));
    end

`ifndef SYNTHESIS
    logic [N*N-1:0][W-1:0] inj_add = '0;      // written by the testbench
    always_comb begin
        for (int e = 0; e < N*N; e++) c_mat[e] = c_core[e] + inj_add[e];
    end
`else
    assign c_mat = c_core;
`endif

    abft_checker #(.N(N), .W(W)) u_chk (
        .clk(clk), .rst_n(rst_n),
        .load(accept), .keep_w(keep_eff), .a_mat(a_mat), .b_mat(b_mat),
        .c_valid(done), .c_mat(c_mat),
        .chk_valid(chk_valid), .err_flag(err_flag), .err_loc_valid(err_loc_valid),
        .err_row(err_row), .err_col(err_col));

endmodule
