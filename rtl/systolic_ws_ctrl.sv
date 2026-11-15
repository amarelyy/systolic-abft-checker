// systolic_ws_ctrl.sv: weight-stationary array plus its control logic
//
// Computes C = A x B for N x N INT8 matrices. Matrices are flat packed buses,
// element [r][c] at index r*N + c.
//
// Sequence after start is accepted (A and B are latched then):
//   LOAD, N cycles:  cycle c shifts row N-1-c of B into the top of the array,
//                    so after N cycles PE[k][j] holds B[k][j].
//   RUN, 3N-1 cycles (t = 0 .. 3N-2):
//                    row k is fed A[t-k][k] (the skew), or 0 outside 0 <= t-k < N.
//                    C[i][j] leaves the bottom of column j at t = i + j + N.
//   done pulses for one cycle after the last C value is captured.
//   c_mat holds the result until the next start.
//
// keep_w: when high at start, the weight load is skipped and the weights already in the
// array are used (b_mat is ignored). Use it only after a multiply that loaded the same B.
// A multiply with keep_w takes 3N - 1 edges instead of 4N.
//
// Back-pressure: while stall is high, the whole datapath and the FSM hold their state
// (the PEs get en = 0), so a stalled cycle changes nothing. start is only accepted in IDLE
// when stall is low; the sender keeps start high until busy goes high.
// From accepted start to done is 4N - 1 cycles plus one cycle per stalled busy cycle.

module systolic_ws_ctrl #(
    parameter int N = 4,
    parameter int W = 18
) (
    input  logic                  clk,
    input  logic                  rst_n,
    input  logic                  stall,
    input  logic                  start,     // ignored while busy or stalled
    input  logic                  keep_w,    // skip the weight load, reuse the loaded B
    input  logic [N*N-1:0][7:0]   a_mat,
    input  logic [N*N-1:0][7:0]   b_mat,
    output logic                  busy,
    output logic                  done,
    output logic [N*N-1:0][W-1:0] c_mat
);

    localparam int LAST_T = 3*N - 2;
    localparam int CW     = $clog2(LAST_T + 1);

    typedef enum logic [1:0] {IDLE, LOAD, RUN} state_t;

    state_t               state;
    logic [CW-1:0]        cnt;       // cycle within LOAD or RUN
    logic [N*N-1:0][7:0]  a_q, b_q;  // latched inputs

    logic                 en, load_w;
    logic [N-1:0][7:0]    w_top, a_left;
    logic [N-1:0][W-1:0]  psum_bottom;

    systolic_ws #(.N(N), .W(W)) u_array (
        .clk         (clk),
        .rst_n       (rst_n),
        .en          (en),
        .load_w      (load_w),
        .w_top       (w_top),
        .a_left      (a_left),
        .psum_bottom (psum_bottom)
    );

    assign busy   = (state != IDLE);
    assign load_w = (state == LOAD);
    assign en     = !stall;

    always_comb begin
        int t;
        t = int'(cnt);
        for (int j = 0; j < N; j++) begin
            w_top[j] = '0;
            if (state == LOAD) w_top[j] = b_q[(N-1-t)*N + j];
        end
        for (int k = 0; k < N; k++) begin
            a_left[k] = '0;
            if (state == RUN && t >= k && t < k + N) a_left[k] = a_q[(t-k)*N + k];
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state <= IDLE;
            cnt   <= '0;
            done  <= 1'b0;
            a_q   <= '0;
            b_q   <= '0;
            c_mat <= '0;
        end else begin
            done <= 1'b0;
            if (!stall) begin
                case (state)
                    IDLE: if (start) begin
                        a_q <= a_mat;
                        cnt <= '0;
                        if (keep_w) begin
                            state <= RUN;
                        end else begin
                            b_q   <= b_mat;
                            state <= LOAD;
                        end
                    end
                    LOAD: if (int'(cnt) == N-1) begin
                        cnt   <= '0;
                        state <= RUN;
                    end else begin
                        cnt <= cnt + 1'b1;
                    end
                    RUN: begin
                        for (int j = 0; j < N; j++) begin
                            // C[i][j] is at the bottom of column j when t = i + j + N
                            if (int'(cnt) >= j + N && int'(cnt) < j + 2*N)
                                c_mat[(int'(cnt) - j - N)*N + j] <= psum_bottom[j];
                        end
                        if (int'(cnt) == LAST_T) begin
                            done  <= 1'b1;
                            state <= IDLE;
                        end else begin
                            cnt <= cnt + 1'b1;
                        end
                    end
                    default: state <= IDLE;
                endcase
            end
        end
    end

`ifndef SYNTHESIS
    // Simulation-only traffic counters: INT8 elements that cross the array boundary.
    // cnt_a: activations fed in, cnt_b: weights fed in, cnt_c: results captured.
    int cnt_a, cnt_b, cnt_c;
    always_ff @(posedge clk) begin
        int da, dc;
        if (!rst_n) begin
            cnt_a <= 0;
            cnt_b <= 0;
            cnt_c <= 0;
        end else if (!stall) begin
            if (state == LOAD) cnt_b <= cnt_b + N;      // one row of B per load cycle
            if (state == RUN) begin
                da = 0;
                dc = 0;
                for (int k = 0; k < N; k++) if (int'(cnt) >= k && int'(cnt) < k + N) da++;
                for (int j = 0; j < N; j++) if (int'(cnt) >= j + N && int'(cnt) < j + 2*N) dc++;
                cnt_a <= cnt_a + da;
                cnt_c <= cnt_c + dc;
            end
        end
    end
`endif

endmodule
