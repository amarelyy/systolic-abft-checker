// systolic_ws.sv: N x N weight-stationary systolic array (step 1.9)
//
// PE[k][j] holds weight B[k][j]. Grid rows are k, grid columns are j.
//   - Activations enter at the left of row k (a_left[k]) and move right.
//   - Partial sums start at 0 at the top of each column and move down.
//   - Weights are shifted in from the top (w_top[j]) while load_w is high.
//   - psum_bottom[j] is the finished column result.
//
// The edges are fed by hand in the step 1.9 test. systolic_ws_ctrl.sv (step 1.10)
// adds the control logic that does the weight load and the input skew.

module systolic_ws #(
    parameter int N = 4,
    parameter int W = 32
) (
    input  logic                clk,
    input  logic                rst_n,
    input  logic                en,
    input  logic                load_w,
    input  logic [N-1:0][7:0]   w_top,        // w_top[j]: weight into the top of column j
    input  logic [N-1:0][7:0]   a_left,       // a_left[k]: activation into the left of row k
    output logic [N-1:0][W-1:0] psum_bottom   // psum_bottom[j]: result out of column j
);

    // Wires between PEs. a_h[k][j] is the activation entering PE[k][j] from the left,
    // psum_v[k][j] and w_v[k][j] enter PE[k][j] from above.
    logic [7:0]   a_h    [N][N+1];
    logic [W-1:0] psum_v [N+1][N];
    logic [7:0]   w_v    [N+1][N];

    for (genvar k = 0; k < N; k++) begin : g_row
        assign a_h[k][0] = a_left[k];

        for (genvar j = 0; j < N; j++) begin : g_col
            pe #(.W(W)) u_pe (
                .clk      (clk),
                .rst_n    (rst_n),
                .en       (en),
                .load_w   (load_w),
                .w_in     (w_v[k][j]),
                .w_out    (w_v[k+1][j]),
                .a_in     (a_h[k][j]),
                .a_out    (a_h[k][j+1]),
                .psum_in  (psum_v[k][j]),
                .psum_out (psum_v[k+1][j])
            );
        end
    end

    for (genvar j = 0; j < N; j++) begin : g_edge
        assign w_v[0][j]      = w_top[j];
        assign psum_v[0][j]   = '0;
        assign psum_bottom[j] = psum_v[N][j];
    end

endmodule
