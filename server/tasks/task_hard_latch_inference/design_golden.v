module mux_latch (
    input a,
    input b,
    input sel,
    output reg y
);

always @(*) begin
    if (sel)
        y = a;
    else
        y = b;
end

endmodule
