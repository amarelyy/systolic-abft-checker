// abft_checker.sv: checksum checker for C = A x B (column and row checksums, mod 2^W)
//
// Column checksum j: sum over i of C[i][j]  must equal  sum over k of colsum(A)[k] * B[k][j].
// Row checksum i:    sum over j of C[i][j]  must equal  sum over k of A[i][k] * rowsum(B)[k].
// All sums wrap mod 2^W like the array accumulators, so a result that wraps does not raise
// an error by itself.
//
// Reference checksums: when a multiply is accepted (load), the checker keeps its own copy of
// A and B. B is only replaced when keep_w is low, matching the weight-stationary array that
// keeps its weights. A small vector-MAC unit (N multipliers for the columns and N for the
// rows) then computes the references over N cycles while the array is still working.
// colsum(A) and rowsum(B) are sums of N INT8 values, so they need 8 + log2(N) bits.
//
// Check: when c_valid is high, c_mat holds the finished result. The sums of c_mat are compared
// with the references, and one cycle later chk_valid pulses with the result:
//   err_flag       some column or row checksum disagrees
//   err_loc_valid  exactly one row and one column disagree (a single wrong element)
//   err_row/col    index of that row and column, only meaningful when err_loc_valid is high
// err_flag and err_loc_valid hold their value until the next multiply is accepted.
//
// The checker is not stalled: stall only freezes the array, and the checker waits for c_valid.

module abft_checker #(
    parameter int N = 4,
    parameter int W = 18
) (
    input  logic                  clk,
    input  logic                  rst_n,

    input  logic                  load,       // a multiply was accepted: copy A and B
    input  logic                  keep_w,     // with load: keep the stored B
    input  logic [N*N-1:0][7:0]   a_mat,
    input  logic [N*N-1:0][7:0]   b_mat,

    input  logic                  c_valid,    // c_mat is the finished result
    input  logic [N*N-1:0][W-1:0] c_mat,

    output logic                  chk_valid,  // one-cycle pulse, one cycle after c_valid
    output logic                  err_flag,
    output logic                  err_loc_valid,
    output logic [$clog2(N)-1:0]  err_row,
    output logic [$clog2(N)-1:0]  err_col
);

    localparam int SW = 8 + $clog2(N);        // width of a sum of N INT8 values
    localparam int KW = $clog2(N);

    // Elements picked out of a packed array are unsigned in SystemVerilog, even if the array is
    // declared signed, so every use of an INT8 element below goes through $signed().
    logic [N*N-1:0][7:0]  a_q, b_q;            // own copies of A and B
    logic signed [SW-1:0] colsum_a [N];        // colsum_a[k] = sum over i of A[i][k]
    logic signed [SW-1:0] rowsum_b [N];        // rowsum_b[k] = sum over j of B[k][j]

    logic [N-1:0][W-1:0] ref_col, ref_row;     // reference checksums
    logic [KW-1:0]       ref_k;
    logic                ref_run, ref_ready;

    logic [N-1:0][W-1:0] out_col, out_row;     // checksums of the output
    logic [N-1:0]        bad_col, bad_row;

    always_comb begin
        for (int k = 0; k < N; k++) begin
            colsum_a[k] = '0;
            rowsum_b[k] = '0;
            for (int x = 0; x < N; x++) begin
                colsum_a[k] += SW'($signed(a_q[x*N + k]));
                rowsum_b[k] += SW'($signed(b_q[k*N + x]));
            end
        end
        for (int x = 0; x < N; x++) begin
            out_col[x] = '0;
            out_row[x] = '0;
            for (int y = 0; y < N; y++) begin
                out_col[x] += c_mat[y*N + x];
                out_row[x] += c_mat[x*N + y];
            end
        end
        for (int x = 0; x < N; x++) begin
            bad_col[x] = (out_col[x] != ref_col[x]);
            bad_row[x] = (out_row[x] != ref_row[x]);
        end
    end

    // Reference checksums: one k per cycle, N cycles after load.
    logic signed [SW+7:0] p_col [N];
    logic signed [SW+7:0] p_row [N];
    always_comb begin
        for (int x = 0; x < N; x++) begin
            p_col[x] = colsum_a[ref_k] * $signed(b_q[int'(ref_k)*N + x]);
            p_row[x] = $signed(a_q[x*N + int'(ref_k)]) * rowsum_b[ref_k];
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            a_q       <= '0;
            b_q       <= '0;
            ref_col   <= '0;
            ref_row   <= '0;
            ref_k     <= '0;
            ref_run   <= 1'b0;
            ref_ready <= 1'b0;
            chk_valid <= 1'b0;
            err_flag  <= 1'b0;
            err_loc_valid <= 1'b0;
            err_row   <= '0;
            err_col   <= '0;
        end else begin
            chk_valid <= c_valid;

            if (load) begin
                a_q <= a_mat;
                if (!keep_w) b_q <= b_mat;
                ref_col       <= '0;
                ref_row       <= '0;
                ref_k         <= '0;
                ref_run       <= 1'b1;
                ref_ready     <= 1'b0;
                err_flag      <= 1'b0;
                err_loc_valid <= 1'b0;
            end else if (ref_run) begin
                for (int x = 0; x < N; x++) begin
                    ref_col[x] <= ref_col[x] + W'(p_col[x]);
                    ref_row[x] <= ref_row[x] + W'(p_row[x]);
                end
                ref_k <= ref_k + 1'b1;
                if (int'(ref_k) == N - 1) begin
                    ref_run   <= 1'b0;
                    ref_ready <= 1'b1;
                end
            end

            if (c_valid) begin
                err_flag      <= (|bad_col) | (|bad_row);
                err_loc_valid <= $onehot(bad_col) && $onehot(bad_row);
                for (int x = 0; x < N; x++) begin
                    if (bad_row[x]) err_row <= KW'(x);
                    if (bad_col[x]) err_col <= KW'(x);
                end
            end
        end
    end

`ifndef SYNTHESIS
`ifndef NO_RTL_ASSERT        // fault-injection runs switch these checks off
    // The references must be ready before the array finishes.
    ref_before_result : assert property (
        @(posedge clk) disable iff (!rst_n)
        c_valid |-> ref_ready
    ) else $error("abft_checker: result arrived before the reference checksums were ready");
`endif
`endif

endmodule
