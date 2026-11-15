// checker_formal.sv: properties of the ABFT checker (rtl/abft_checker.sv), for SymbiYosys.
//
// IW is the width of the input elements. The identity being proved is algebra and its proof
// grows very quickly with IW, so the proofs run for IW = 3 to 6, not for the real IW = 8.
//
// Scenario: one multiply. A and B are free (any values). load happens once, in cycle 1, and
// the result arrives (c_valid) DELAY cycles later (the reference needs 4 cycles, the array at
// least 11, so DELAY = 5 is the earliest the checker could ever be asked). The result is the true product A x B mod 2^W (MODE 0) or the true product with exactly
// one element wrong by any nonzero amount at any position (MODE 1).
//   MODE 0: the checker must not raise the error flag, for every A and B.
//   MODE 1: the checker must raise the flag and report exactly the wrong row and column.
//   MODE 2: protocol only: the result is free (any value), only the timing and flag-consistency
//           properties are checked. This needs no arithmetic and proves quickly.

module checker_formal #(
    parameter int W     = 10,
    parameter int IW    = 3,      // width of the input elements; the real design uses 8
    parameter int MODE  = 0,
    parameter int DELAY = 5
) (
    input  logic            clk,
    input  logic            rst_n,
    input  logic            load,
    input  logic            c_valid,
    input  logic [16*IW-1:0] a_flat,
    input  logic [16*IW-1:0] b_flat
);
    logic [15:0][IW-1:0] a_mat, b_mat;
    logic [15:0][W-1:0]  c_mat;
    assign a_mat = a_flat;
    assign b_mat = b_flat;
    logic       chk_valid, err_flag, err_loc_valid;
    logic [1:0] err_row, err_col;

    abft_checker #(.N(4), .W(W), .IW(IW)) dut (.clk(clk), .rst_n(rst_n), .load(load), .keep_w(1'b0),
        .a_mat(a_mat), .b_mat(b_mat), .c_valid(c_valid), .c_mat(c_mat), .chk_valid(chk_valid),
        .err_flag(err_flag), .err_loc_valid(err_loc_valid), .err_row(err_row), .err_col(err_col));

    logic past_valid = 1'b0;
    always @(posedge clk) past_valid <= 1'b1;
    always @(*) if (!past_valid) assume (!rst_n);
    always @(*) if (past_valid) assume (rst_n);          // reset only in the first cycle

    // --- the scenario -----------------------------------------------------------------
    logic [4:0]       step = 5'd0;                   // cycle number after reset
    logic [15:0][IW-1:0] a0, b0;                            // the A and B captured at load
    always @(posedge clk) begin
        if (step != 5'd31) step <= step + 5'd1;
        if (load && rst_n) begin a0 <= a_mat; b0 <= b_mat; end
    end
    always @(*) begin
        assume (load    == (step == 5'd1));              // one load, in cycle 1
        assume (c_valid == (step == 5'd1 + DELAY));      // one result, DELAY cycles later
    end

    // the true product mod 2^W, from plain integer arithmetic. Every product is computed at its
    // own exact width (2*IW bits): in Verilog a product takes the width of the whole expression,
    // and a W+17 bit multiplier per element made the solver's job far larger than it needs to be.
    function automatic logic signed [2*IW-1:0] mul(input logic signed [IW-1:0] x,
                                                   input logic signed [IW-1:0] y);
        mul = x * y;
    endfunction

    logic [15:0][W-1:0] golden;
    always @(*) begin
        for (int i = 0; i < 4; i++)
            for (int j = 0; j < 4; j++) begin
                logic [W-1:0] acc;
                acc = '0;
                for (int k = 0; k < 4; k++)
                    acc = acc + W'(mul(a0[i*4+k], b0[k*4+j]));   // sign-extended, wraps mod 2^W
                golden[i*4+j] = acc;
            end
    end

    (* anyconst *) logic [1:0]   wi, wj;                 // the wrong element (MODE 1)
    (* anyconst *) logic [W-1:0] wd;                     // by how much (MODE 1)
    always @(*) begin
        if (MODE == 1) assume (wd != '0);
        if (c_valid && MODE != 2) begin
            for (int e = 0; e < 16; e++) begin
                if (MODE == 1 && e == int'({wi, wj})) assume (c_mat[e] == golden[e] + wd);
                else                                  assume (c_mat[e] == golden[e]);
            end
        end
    end

    // --- the properties ---------------------------------------------------------------
    always @(posedge clk) if (past_valid && $past(rst_n)) begin
        assert (chk_valid == $past(c_valid));            // report exactly one cycle after the result
        if ($past(c_valid) && MODE != 2) begin
            if (MODE == 0) begin
                assert (!err_flag);                      // no false alarm, for every A and B
                assert (!err_loc_valid);
            end else begin
                assert (err_flag);                       // any single wrong element is detected ...
                assert (err_loc_valid);
                assert (err_row == $past(wi));           // ... and located exactly
                assert (err_col == $past(wj));
            end
        end
        if (err_loc_valid) assert (err_flag);
    end

    always @(posedge clk) cover (past_valid && chk_valid);
endmodule
