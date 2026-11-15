// pe_formal.sv: properties of the weight-stationary PE (rtl/pe.sv), for SymbiYosys.
// The inputs are free (any value, any cycle). The expected values are computed with
// plain integer arithmetic in a wider word, independent of how the RTL writes the sum.

module pe_formal #(
    parameter int W = 18
) (
    input  logic                clk,
    input  logic                rst_n,
    input  logic                en,
    input  logic                load_w,
    input  logic signed [7:0]   w_in,
    input  logic signed [7:0]   a_in,
    input  logic signed [W-1:0] psum_in
);
    logic signed [7:0]   w_out, a_out;
    logic signed [W-1:0] psum_out;

    pe #(.W(W)) dut (.clk(clk), .rst_n(rst_n), .en(en), .load_w(load_w), .w_in(w_in),
                     .w_out(w_out), .a_in(a_in), .a_out(a_out), .psum_in(psum_in),
                     .psum_out(psum_out));

    logic past_valid = 1'b0;
    always @(posedge clk) past_valid <= 1'b1;
    always @(*) if (!past_valid) assume (!rst_n);          // start from reset

    // expected next accumulator value, computed in W + 17 bits so nothing can overflow
    logic signed [W+16:0] full;
    always @(*) full = $signed({{17{psum_in[W-1]}}, psum_in}) + $signed(a_in) * $signed(w_out);
    logic [W-1:0] expected_psum;
    always @(posedge clk) expected_psum <= full[W-1:0];    // what psum_out must be next cycle

    always @(posedge clk) if (past_valid) begin
        // reset: everything is zero one cycle after rst_n was low
        if ($past(!rst_n)) begin
            assert (psum_out == '0);
            assert (a_out == '0);
            assert (w_out == '0);
        end
        if ($past(rst_n)) begin
            if ($past(en)) begin
                // the multiply-accumulate, wrapped mod 2^W
                assert (psum_out == expected_psum);
                // activations pass through unchanged
                assert (a_out == $past(a_in));
                // the weight changes only when load_w was high, and then takes w_in
                if ($past(load_w)) assert (w_out == $past(w_in));
                else               assert (w_out == $past(w_out));
            end else begin
                // en low: every register holds its value
                assert (psum_out == $past(psum_out));
                assert (a_out    == $past(a_out));
                assert (w_out    == $past(w_out));
            end
        end
    end

    // not vacuous: a multiply-accumulate with a nonzero result is reachable
    always @(posedge clk) cover (past_valid && $past(rst_n) && $past(en) && psum_out != '0);
endmodule
