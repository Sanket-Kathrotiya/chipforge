module mux_latch (
    input a,
    input b,
    input sel,
    output reg y
);

always @(*) begin
    if (sel)
        y = a;
    // missing else branch — latch inferred
end

endmodule
