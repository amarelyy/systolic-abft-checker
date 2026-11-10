// pe_os.sv: processing element for the output-stationary array
//
// The accumulator stays in the PE. Each cycle it adds a_in * b_in.
// a passes to the right through a_out, b passes down through b_out.
// clr zeroes the accumulator and both pass-through registers (start of a multiply), so no
// data from an earlier multiply can leak into the next one.
// en is the clock enable: when low every register holds its value.

module pe_os #(
    parameter int W = 18                    // accumulator width
) (
    input  logic                clk,
    input  logic                rst_n,      // active-low synchronous reset
    input  logic                en,
    input  logic                clr,

    input  logic signed [7:0]   a_in,
    output logic signed [7:0]   a_out,
    input  logic signed [7:0]   b_in,
    output logic signed [7:0]   b_out,

    output logic signed [W-1:0] acc
);

    if (W < 16) begin : g_w_check
        $error("pe_os: W must be at least 16, got %0d", W);
    end

    logic signed [15:0] prod;
    assign prod = a_in * b_in;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            acc   <= '0;
            a_out <= '0;
            b_out <= '0;
        end else if (en) begin
            if (clr) begin
                acc   <= '0;
                a_out <= '0;
                b_out <= '0;
            end else begin
                acc   <= acc + W'(prod);   // W'() sign-extends prod, sum wraps mod 2^W
                a_out <= a_in;
                b_out <= b_in;
            end
        end
    end

`ifndef SYNTHESIS
    // acc == previous acc + a*b, unless the previous cycle was a clear or a stall.
    a_mac : assert property (
        @(posedge clk) disable iff (!rst_n)
        $past(rst_n) && $past(en) && !$past(clr) |->
            acc == W'($past(acc) + $past(a_in) * $past(b_in))
    ) else $error("pe_os: acc=%0d, expected acc + a*b", acc);
`endif

endmodule
