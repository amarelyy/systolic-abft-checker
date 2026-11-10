// systolic_os_ctrl.sv: output-stationary array plus its control logic
//
// Same ports and handshake as systolic_ws_ctrl, so the same testbench drives both.
//
// Sequence after start is accepted (A and B are latched, accumulators are cleared):
//   RUN, 3N-2 cycles (t = 0 .. 3N-3):
//     row i is fed A[i][t-i] for 0 <= t-i < N, column j is fed B[t-j][j] for 0 <= t-j < N,
//     so A[i][k] and B[k][j] meet in PE[i][j] at t = i + j + k.
//   done pulses for one cycle after the last accumulation. c_mat reads the accumulators
//   directly, so it holds the result until the next start clears them.
//
// There is no weight-load phase. The state encoding keeps IDLE = 0 and RUN = 2 like the
// weight-stationary control, so the monitor can read `state` from either design.
//
// Back-pressure: while stall is high everything holds its state (see systolic_ws_ctrl.sv).
// From the accepting edge to done is 3N - 1 edges plus one per stalled busy cycle.

module systolic_os_ctrl #(
    parameter int N = 4,
    parameter int W = 18
) (
    input  logic                  clk,
    input  logic                  rst_n,
    input  logic                  stall,
    input  logic                  start,     // ignored while busy or stalled
    input  logic [N*N-1:0][7:0]   a_mat,
    input  logic [N*N-1:0][7:0]   b_mat,
    output logic                  busy,
    output logic                  done,
    output logic [N*N-1:0][W-1:0] c_mat
);

    localparam int LAST_T = 3*N - 3;
    localparam int CW     = $clog2(LAST_T + 1);

    typedef enum logic [1:0] {IDLE = 2'd0, UNUSED = 2'd1, RUN = 2'd2} state_t;

    state_t               state;
    logic [CW-1:0]        cnt;
    logic [N*N-1:0][7:0]  a_q, b_q;

    logic                 en, accept;
    logic [N-1:0][7:0]    a_left, b_top;

    assign busy   = (state != IDLE);
    assign en     = !stall;
    assign accept = (state == IDLE) && start && !stall;

    systolic_os #(.N(N), .W(W)) u_array (
        .clk     (clk),
        .rst_n   (rst_n),
        .en      (en),
        .clr     (accept),
        .a_left  (a_left),
        .b_top   (b_top),
        .acc_mat (c_mat)
    );

    always_comb begin
        int t;
        t = int'(cnt);
        for (int i = 0; i < N; i++) begin
            a_left[i] = '0;
            if (state == RUN && t >= i && t < i + N) a_left[i] = a_q[i*N + (t-i)];
        end
        for (int j = 0; j < N; j++) begin
            b_top[j] = '0;
            if (state == RUN && t >= j && t < j + N) b_top[j] = b_q[(t-j)*N + j];
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state <= IDLE;
            cnt   <= '0;
            done  <= 1'b0;
            a_q   <= '0;
            b_q   <= '0;
        end else begin
            done <= 1'b0;
            if (!stall) begin
                if (accept) begin
                    a_q   <= a_mat;
                    b_q   <= b_mat;
                    cnt   <= '0;
                    state <= RUN;
                end else if (state == RUN) begin
                    if (int'(cnt) == LAST_T) begin
                        done  <= 1'b1;
                        state <= IDLE;
                    end else begin
                        cnt <= cnt + 1'b1;
                    end
                end
            end
        end
    end

endmodule
