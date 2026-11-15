// ctrl_formal.sv: handshake and timing properties of the array controls, for SymbiYosys.
// OS = 0 checks systolic_ws_ctrl, OS = 1 checks systolic_os_ctrl. Inputs are free: start,
// stall, keep_w and both matrices may be anything in any cycle.
//
// "accept" is the cycle in which the control takes start: idle, start high, stall low.

module ctrl_formal #(
    parameter int W  = 18,
    parameter int OS = 0
) (
    input  logic                clk,
    input  logic                rst_n,
    input  logic                stall,
    input  logic                start,
    input  logic                keep_w,
    input  logic [16*8-1:0]     a_flat,
    input  logic [16*8-1:0]     b_flat
);
    logic [15:0][7:0]   a_mat, b_mat;
    logic [15:0][W-1:0] c_mat;
    logic               busy, done;
    assign a_mat = a_flat;
    assign b_mat = b_flat;

    if (OS == 0) begin : g
        systolic_ws_ctrl #(.N(4), .W(W)) dut (.clk(clk), .rst_n(rst_n), .stall(stall), .start(start),
            .keep_w(keep_w), .a_mat(a_mat), .b_mat(b_mat), .busy(busy), .done(done), .c_mat(c_mat));
    end else begin : g
        systolic_os_ctrl #(.N(4), .W(W)) dut (.clk(clk), .rst_n(rst_n), .stall(stall), .start(start),
            .keep_w(keep_w), .a_mat(a_mat), .b_mat(b_mat), .busy(busy), .done(done), .c_mat(c_mat));
    end

    // Non-stalled clock edges from the accepting edge to the edge that sets done. Counting the
    // accepting edge itself these are the numbers the simulation measured: 16 and 11. A
    // weight-stationary multiply that reuses the loaded weights (keep_w high at accept) skips
    // the 4-cycle load and needs 11 + 1 = 12 edges; formal verification found that case itself.
    logic keep_q;                                       // keep_w as it was when start was accepted
    wire  [7:0] LAT = (OS == 0) ? (keep_q ? 8'd11 : 8'd15) : 8'd10;

    logic past_valid = 1'b0;
    always @(posedge clk) past_valid <= 1'b1;
    always @(*) if (!past_valid) assume (!rst_n);

    logic accept;
    assign accept = !busy && start && !stall;

    logic [7:0] nb;                                     // non-stalled busy edges since accept
    always @(posedge clk) begin
        if (accept) keep_q <= keep_w;
        if (!rst_n || accept) nb <= 8'd0;
        else if (busy && !stall) nb <= nb + 8'd1;
    end

    always @(posedge clk) if (past_valid) begin
        // after reset the control is idle and silent
        if ($past(!rst_n)) begin
            assert (!busy);
            assert (!done);
        end
        if ($past(rst_n)) begin
            // 1. busy starts only when start was accepted, and an accepted start does start it
            if (!$past(busy) && busy) assert ($past(start) && !$past(stall));
            if (!$past(busy) && $past(start) && !$past(stall)) assert (busy);
            // 2. busy ends only together with the done pulse
            if ($past(busy) && !busy) assert (done);
            // 3. done is a one-cycle pulse, only when the control has just gone idle
            if (done) begin
                assert (!busy);
                assert ($past(busy));
                assert (!$past(done));
            end
            // 4. a stalled cycle freezes the control: still busy or idle as before, no done
            if ($past(stall)) begin
                assert (busy == $past(busy));
                assert (!done);
            end
        end
        // 5. timing: done comes after exactly LAT non-stalled edges, never before or later
        if (done) assert (nb == LAT);
        if (busy) assert (nb < LAT);
    end

    // not vacuous
    always @(posedge clk) begin
        cover (past_valid && done);
        cover (past_valid && busy && stall);
        cover (past_valid && done && $past(stall, 3));
    end
endmodule
