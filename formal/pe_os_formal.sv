// pe_os_formal.sv: properties of the output-stationary PE (rtl/pe_os.sv), for SymbiYosys.

module pe_os_formal #(
    parameter int W = 18
) (
    input  logic              clk,
    input  logic              rst_n,
    input  logic              en,
    input  logic              clr,
    input  logic signed [7:0] a_in,
    input  logic signed [7:0] b_in
);
    logic signed [7:0]   a_out, b_out;
    logic signed [W-1:0] acc;

    pe_os #(.W(W)) dut (.clk(clk), .rst_n(rst_n), .en(en), .clr(clr), .a_in(a_in), .a_out(a_out),
                        .b_in(b_in), .b_out(b_out), .acc(acc));

    logic past_valid = 1'b0;
    always @(posedge clk) past_valid <= 1'b1;
    always @(*) if (!past_valid) assume (!rst_n);

    logic signed [W+16:0] full;
    always @(*) full = $signed({{17{acc[W-1]}}, acc}) + $signed(a_in) * $signed(b_in);
    logic [W-1:0] expected_acc;
    always @(posedge clk) expected_acc <= full[W-1:0];

    always @(posedge clk) if (past_valid) begin
        if ($past(!rst_n)) begin
            assert (acc == '0);
            assert (a_out == '0);
            assert (b_out == '0);
        end
        if ($past(rst_n)) begin
            if ($past(en)) begin
                if ($past(clr)) assert (acc == '0);               // clear
                else            assert (acc == expected_acc);     // accumulate, wrapped mod 2^W
                assert (a_out == $past(a_in));                    // pass-through, no clear needed
                assert (b_out == $past(b_in));
            end else begin
                assert (acc   == $past(acc));
                assert (a_out == $past(a_out));
                assert (b_out == $past(b_out));
            end
        end
    end

    always @(posedge clk) cover (past_valid && $past(rst_n) && $past(en) && !$past(clr) && acc != '0);
endmodule
