`timescale 1ns/1ps

module tb_mux_latch;

reg a;
reg b;
reg sel;
wire y;

mux_latch uut (
    .a(a),
    .b(b),
    .sel(sel),
    .y(y)
);

initial begin
    $display("sel a b | y");
    $display("-----------");

    sel=0; a=0; b=0; #10;
    $display(" %b  %b %b | %b", sel, a, b, y);

    sel=0; a=0; b=1; #10;
    $display(" %b  %b %b | %b", sel, a, b, y);

    sel=0; a=1; b=0; #10;
    $display(" %b  %b %b | %b", sel, a, b, y);

    sel=0; a=1; b=1; #10;
    $display(" %b  %b %b | %b", sel, a, b, y);

    sel=1; a=0; b=0; #10;
    $display(" %b  %b %b | %b", sel, a, b, y);

    sel=1; a=0; b=1; #10;
    $display(" %b  %b %b | %b", sel, a, b, y);

    sel=1; a=1; b=0; #10;
    $display(" %b  %b %b | %b", sel, a, b, y);

    sel=1; a=1; b=1; #10;
    $display(" %b  %b %b | %b", sel, a, b, y);

    $finish;
end

endmodule
