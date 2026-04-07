module full_adder (
    input a,
    input b,
    input cin,
    output sum,
    output cout
);

wire x1;

assign x1 = a ^ b;
assign sum = x1 ^ cin;
assign cout = (a ^ b) | (b ^ cin) | (a ^ cin);

endmodule
