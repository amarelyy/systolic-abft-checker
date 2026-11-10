// systolic_os.sv: N x N output-stationary systolic array
//
// PE[i][j] accumulates C[i][j] = sum over k of A[i][k] * B[k][j].
//   - A enters at the left of row i (a_left[i]) and moves right.
//   - B enters at the top of column j (b_top[j]) and moves down.
//   - clr zeroes all accumulators and pass-through registers.
//   - acc_mat holds the accumulators, element [i][j] at index i*N + j.
//
// systolic_os_ctrl.sv adds the control logic that applies the input skew.

module systolic_os #(
    parameter int N = 4,
    parameter int W = 18
) (
    input  logic                  clk,
    input  logic                  rst_n,
    input  logic                  en,
    input  logic                  clr,
    input  logic [N-1:0][7:0]     a_left,
    input  logic [N-1:0][7:0]     b_top,
    output logic [N*N-1:0][W-1:0] acc_mat
);

    // a_h[i][j] enters PE[i][j] from the left, b_v[i][j] enters PE[i][j] from above.
    logic [7:0] a_h [N][N+1];
    logic [7:0] b_v [N+1][N];

    for (genvar i = 0; i < N; i++) begin : g_row
        assign a_h[i][0] = a_left[i];

        for (genvar j = 0; j < N; j++) begin : g_col
            pe_os #(.W(W)) u_pe (
                .clk   (clk),
                .rst_n (rst_n),
                .en    (en),
                .clr   (clr),
                .a_in  (a_h[i][j]),
                .a_out (a_h[i][j+1]),
                .b_in  (b_v[i][j]),
                .b_out (b_v[i+1][j]),
                .acc   (acc_mat[i*N + j])
            );
        end
    end

    for (genvar j = 0; j < N; j++) begin : g_edge
        assign b_v[0][j] = b_top[j];
    end

endmodule
