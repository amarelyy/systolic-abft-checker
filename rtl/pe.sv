// pe.sv: processing element
//
// One multiply-accumulate per cycle: psum_out <= psum_in + a_in * w.
// a and w are signed INT8. psum is W bits and wraps mod 2^W, like a real register.
//
// Weight-stationary use: while load_w is high, w shifts down the column
// (w <= w_in, w_out = w), so a 4-row column is loaded in 4 cycles.
// Activations pass to the right through a_out, psums pass down through psum_out.
//
// en is the clock enable. When en is low every register holds its value.
// systolic_ws_ctrl.sv drives it low to stall the array (back-pressure).

module pe #(
    parameter int W = 18                    // accumulator width
) (
    input  logic                clk,
    input  logic                rst_n,      // active-low synchronous reset
    input  logic                en,

    input  logic                load_w,
    input  logic signed [7:0]   w_in,       // from the PE above (weight load)
    output logic signed [7:0]   w_out,      // to the PE below

    input  logic signed [7:0]   a_in,       // from the PE to the left
    output logic signed [7:0]   a_out,      // to the PE to the right

    input  logic signed [W-1:0] psum_in,    // from the PE above
    output logic signed [W-1:0] psum_out    // to the PE below
);

    // A product can be 16 bits (-128 * -128 = 16384), so W below 16 cannot hold one.
    if (W < 16) begin : g_w_check
        $error("pe: W must be at least 16, got %0d", W);
    end

    logic signed [7:0]   w;
    logic signed [15:0]  prod;
    logic signed [W-1:0] psum_next;

    assign prod      = a_in * w;
    assign psum_next = psum_in + W'(prod);   // W'() sign-extends prod, sum wraps mod 2^W
    assign w_out     = w;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            w        <= '0;
            a_out    <= '0;
            psum_out <= '0;
        end else if (en) begin
            if (load_w) w <= w_in;
            a_out    <= a_in;
            psum_out <= psum_next;
        end
    end

`ifndef SYNTHESIS
    // psum_out == psum_in + a*w, one cycle later.
    // The right side is written independently of psum_next on purpose: all operands are
    // signed, so they are sign-extended to W bits and the product is taken mod 2^W.
    a_mac : assert property (
        @(posedge clk) disable iff (!rst_n)
        $past(rst_n) && $past(en) |->
            psum_out == W'($past(psum_in) + $past(a_in) * $past(w))
    ) else $error("pe: psum_out=%0d, expected psum_in + a*w", psum_out);
`endif

endmodule
