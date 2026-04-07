// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vsim.h for the primary calling header

#include "Vsim__pch.h"

VlCoroutine Vsim___024root___eval_initial__TOP__Vtiming__0(Vsim___024root* vlSelf);

void Vsim___024root___eval_initial(Vsim___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vsim___024root___eval_initial\n"); );
    Vsim__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    Vsim___024root___eval_initial__TOP__Vtiming__0(vlSelf);
    vlSelfRef.__Vm_traceActivity[1U] = 1U;
}

VlCoroutine Vsim___024root___eval_initial__TOP__Vtiming__0(Vsim___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vsim___024root___eval_initial__TOP__Vtiming__0\n"); );
    Vsim__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    VL_WRITEF_NX("a b cin | sum cout\n-------------------\n",0);
    vlSelfRef.tb_full_adder__DOT__a = 0U;
    vlSelfRef.tb_full_adder__DOT__b = 0U;
    vlSelfRef.tb_full_adder__DOT__cin = 0U;
    co_await vlSelfRef.__VdlySched.delay(0x0000000000002710ULL, 
                                         nullptr, "/workspace/.tmp_verilator/testbench.sv", 
                                         26);
    vlSelfRef.__Vm_traceActivity[2U] = 1U;
    VL_WRITEF_NX("%b %b  %b  |  %b   %b\n",5, '#',1,vlSelfRef.tb_full_adder__DOT__a
                 , '#',1,(IData)(vlSelfRef.tb_full_adder__DOT__b)
                 , '#',1,vlSelfRef.tb_full_adder__DOT__cin
                 , '#',1,(IData)(vlSelfRef.tb_full_adder__DOT__uut__DOT__sum)
                 , '#',1,vlSelfRef.tb_full_adder__DOT__uut__DOT__cout);
    vlSelfRef.tb_full_adder__DOT__a = 0U;
    vlSelfRef.tb_full_adder__DOT__b = 0U;
    vlSelfRef.tb_full_adder__DOT__cin = 1U;
    co_await vlSelfRef.__VdlySched.delay(0x0000000000002710ULL, 
                                         nullptr, "/workspace/.tmp_verilator/testbench.sv", 
                                         29);
    vlSelfRef.__Vm_traceActivity[2U] = 1U;
    VL_WRITEF_NX("%b %b  %b  |  %b   %b\n",5, '#',1,vlSelfRef.tb_full_adder__DOT__a
                 , '#',1,(IData)(vlSelfRef.tb_full_adder__DOT__b)
                 , '#',1,vlSelfRef.tb_full_adder__DOT__cin
                 , '#',1,(IData)(vlSelfRef.tb_full_adder__DOT__uut__DOT__sum)
                 , '#',1,vlSelfRef.tb_full_adder__DOT__uut__DOT__cout);
    vlSelfRef.tb_full_adder__DOT__a = 0U;
    vlSelfRef.tb_full_adder__DOT__b = 1U;
    vlSelfRef.tb_full_adder__DOT__cin = 0U;
    co_await vlSelfRef.__VdlySched.delay(0x0000000000002710ULL, 
                                         nullptr, "/workspace/.tmp_verilator/testbench.sv", 
                                         32);
    vlSelfRef.__Vm_traceActivity[2U] = 1U;
    VL_WRITEF_NX("%b %b  %b  |  %b   %b\n",5, '#',1,vlSelfRef.tb_full_adder__DOT__a
                 , '#',1,(IData)(vlSelfRef.tb_full_adder__DOT__b)
                 , '#',1,vlSelfRef.tb_full_adder__DOT__cin
                 , '#',1,(IData)(vlSelfRef.tb_full_adder__DOT__uut__DOT__sum)
                 , '#',1,vlSelfRef.tb_full_adder__DOT__uut__DOT__cout);
    vlSelfRef.tb_full_adder__DOT__a = 0U;
    vlSelfRef.tb_full_adder__DOT__b = 1U;
    vlSelfRef.tb_full_adder__DOT__cin = 1U;
    co_await vlSelfRef.__VdlySched.delay(0x0000000000002710ULL, 
                                         nullptr, "/workspace/.tmp_verilator/testbench.sv", 
                                         35);
    vlSelfRef.__Vm_traceActivity[2U] = 1U;
    VL_WRITEF_NX("%b %b  %b  |  %b   %b\n",5, '#',1,vlSelfRef.tb_full_adder__DOT__a
                 , '#',1,(IData)(vlSelfRef.tb_full_adder__DOT__b)
                 , '#',1,vlSelfRef.tb_full_adder__DOT__cin
                 , '#',1,(IData)(vlSelfRef.tb_full_adder__DOT__uut__DOT__sum)
                 , '#',1,vlSelfRef.tb_full_adder__DOT__uut__DOT__cout);
    vlSelfRef.tb_full_adder__DOT__a = 1U;
    vlSelfRef.tb_full_adder__DOT__b = 0U;
    vlSelfRef.tb_full_adder__DOT__cin = 0U;
    co_await vlSelfRef.__VdlySched.delay(0x0000000000002710ULL, 
                                         nullptr, "/workspace/.tmp_verilator/testbench.sv", 
                                         38);
    vlSelfRef.__Vm_traceActivity[2U] = 1U;
    VL_WRITEF_NX("%b %b  %b  |  %b   %b\n",5, '#',1,vlSelfRef.tb_full_adder__DOT__a
                 , '#',1,(IData)(vlSelfRef.tb_full_adder__DOT__b)
                 , '#',1,vlSelfRef.tb_full_adder__DOT__cin
                 , '#',1,(IData)(vlSelfRef.tb_full_adder__DOT__uut__DOT__sum)
                 , '#',1,vlSelfRef.tb_full_adder__DOT__uut__DOT__cout);
    vlSelfRef.tb_full_adder__DOT__a = 1U;
    vlSelfRef.tb_full_adder__DOT__b = 0U;
    vlSelfRef.tb_full_adder__DOT__cin = 1U;
    co_await vlSelfRef.__VdlySched.delay(0x0000000000002710ULL, 
                                         nullptr, "/workspace/.tmp_verilator/testbench.sv", 
                                         41);
    vlSelfRef.__Vm_traceActivity[2U] = 1U;
    VL_WRITEF_NX("%b %b  %b  |  %b   %b\n",5, '#',1,vlSelfRef.tb_full_adder__DOT__a
                 , '#',1,(IData)(vlSelfRef.tb_full_adder__DOT__b)
                 , '#',1,vlSelfRef.tb_full_adder__DOT__cin
                 , '#',1,(IData)(vlSelfRef.tb_full_adder__DOT__uut__DOT__sum)
                 , '#',1,vlSelfRef.tb_full_adder__DOT__uut__DOT__cout);
    vlSelfRef.tb_full_adder__DOT__a = 1U;
    vlSelfRef.tb_full_adder__DOT__b = 1U;
    vlSelfRef.tb_full_adder__DOT__cin = 0U;
    co_await vlSelfRef.__VdlySched.delay(0x0000000000002710ULL, 
                                         nullptr, "/workspace/.tmp_verilator/testbench.sv", 
                                         44);
    vlSelfRef.__Vm_traceActivity[2U] = 1U;
    VL_WRITEF_NX("%b %b  %b  |  %b   %b\n",5, '#',1,vlSelfRef.tb_full_adder__DOT__a
                 , '#',1,(IData)(vlSelfRef.tb_full_adder__DOT__b)
                 , '#',1,vlSelfRef.tb_full_adder__DOT__cin
                 , '#',1,(IData)(vlSelfRef.tb_full_adder__DOT__uut__DOT__sum)
                 , '#',1,vlSelfRef.tb_full_adder__DOT__uut__DOT__cout);
    vlSelfRef.tb_full_adder__DOT__a = 1U;
    vlSelfRef.tb_full_adder__DOT__b = 1U;
    vlSelfRef.tb_full_adder__DOT__cin = 1U;
    co_await vlSelfRef.__VdlySched.delay(0x0000000000002710ULL, 
                                         nullptr, "/workspace/.tmp_verilator/testbench.sv", 
                                         47);
    vlSelfRef.__Vm_traceActivity[2U] = 1U;
    VL_WRITEF_NX("%b %b  %b  |  %b   %b\n",5, '#',1,vlSelfRef.tb_full_adder__DOT__a
                 , '#',1,(IData)(vlSelfRef.tb_full_adder__DOT__b)
                 , '#',1,vlSelfRef.tb_full_adder__DOT__cin
                 , '#',1,(IData)(vlSelfRef.tb_full_adder__DOT__uut__DOT__sum)
                 , '#',1,vlSelfRef.tb_full_adder__DOT__uut__DOT__cout);
    VL_FINISH_MT("/workspace/.tmp_verilator/testbench.sv", 50, "");
    vlSelfRef.__Vm_traceActivity[2U] = 1U;
    co_return;
}

void Vsim___024root___eval_triggers_vec__act(Vsim___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vsim___024root___eval_triggers_vec__act\n"); );
    Vsim__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    vlSelfRef.__VactTriggered[0U] = (QData)((IData)(vlSelfRef.__VdlySched.awaitingCurrentTime()));
}

bool Vsim___024root___trigger_anySet__act(const VlUnpacked<QData/*63:0*/, 1> &in) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vsim___024root___trigger_anySet__act\n"); );
    // Locals
    IData/*31:0*/ n;
    // Body
    n = 0U;
    do {
        if (in[n]) {
            return (1U);
        }
        n = ((IData)(1U) + n);
    } while ((1U > n));
    return (0U);
}

void Vsim___024root___act_sequent__TOP__0(Vsim___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vsim___024root___act_sequent__TOP__0\n"); );
    Vsim__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    vlSelfRef.tb_full_adder__DOT__uut__DOT__sum = ((IData)(vlSelfRef.tb_full_adder__DOT__cin) 
                                                   ^ 
                                                   ((IData)(vlSelfRef.tb_full_adder__DOT__a) 
                                                    ^ (IData)(vlSelfRef.tb_full_adder__DOT__b)));
    vlSelfRef.tb_full_adder__DOT__uut__DOT__cout = 
        (((IData)(vlSelfRef.tb_full_adder__DOT__a) 
          & (IData)(vlSelfRef.tb_full_adder__DOT__b)) 
         | ((IData)(vlSelfRef.tb_full_adder__DOT__cin) 
            & ((IData)(vlSelfRef.tb_full_adder__DOT__a) 
               | (IData)(vlSelfRef.tb_full_adder__DOT__b))));
}

void Vsim___024root___eval_act(Vsim___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vsim___024root___eval_act\n"); );
    Vsim__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    if ((1ULL & vlSelfRef.__VactTriggered[0U])) {
        Vsim___024root___act_sequent__TOP__0(vlSelf);
    }
}

void Vsim___024root___eval_nba(Vsim___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vsim___024root___eval_nba\n"); );
    Vsim__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    if ((1ULL & vlSelfRef.__VnbaTriggered[0U])) {
        Vsim___024root___act_sequent__TOP__0(vlSelf);
    }
}

void Vsim___024root___timing_resume(Vsim___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vsim___024root___timing_resume\n"); );
    Vsim__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    if ((1ULL & vlSelfRef.__VactTriggered[0U])) {
        vlSelfRef.__VdlySched.resume();
    }
}

void Vsim___024root___trigger_orInto__act_vec_vec(VlUnpacked<QData/*63:0*/, 1> &out, const VlUnpacked<QData/*63:0*/, 1> &in) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vsim___024root___trigger_orInto__act_vec_vec\n"); );
    // Locals
    IData/*31:0*/ n;
    // Body
    n = 0U;
    do {
        out[n] = (out[n] | in[n]);
        n = ((IData)(1U) + n);
    } while ((0U >= n));
}

#ifdef VL_DEBUG
VL_ATTR_COLD void Vsim___024root___dump_triggers__act(const VlUnpacked<QData/*63:0*/, 1> &triggers, const std::string &tag);
#endif  // VL_DEBUG

bool Vsim___024root___eval_phase__act(Vsim___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vsim___024root___eval_phase__act\n"); );
    Vsim__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Locals
    CData/*0:0*/ __VactExecute;
    // Body
    Vsim___024root___eval_triggers_vec__act(vlSelf);
    Vsim___024root___trigger_orInto__act_vec_vec(vlSelfRef.__VactTriggered, vlSelfRef.__VactTriggeredAcc);
#ifdef VL_DEBUG
    if (VL_UNLIKELY(vlSymsp->_vm_contextp__->debug())) {
        Vsim___024root___dump_triggers__act(vlSelfRef.__VactTriggered, "act"s);
    }
#endif
    Vsim___024root___trigger_orInto__act_vec_vec(vlSelfRef.__VnbaTriggered, vlSelfRef.__VactTriggered);
    __VactExecute = Vsim___024root___trigger_anySet__act(vlSelfRef.__VactTriggered);
    if (__VactExecute) {
        vlSelfRef.__VactTriggeredAcc.fill(0ULL);
        Vsim___024root___timing_resume(vlSelf);
        Vsim___024root___eval_act(vlSelf);
    }
    return (__VactExecute);
}

bool Vsim___024root___eval_phase__inact(Vsim___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vsim___024root___eval_phase__inact\n"); );
    Vsim__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Locals
    CData/*0:0*/ __VinactExecute;
    // Body
    __VinactExecute = vlSelfRef.__VdlySched.awaitingZeroDelay();
    if (__VinactExecute) {
        VL_FATAL_MT("/workspace/.tmp_verilator/testbench.sv", 3, "", "ZERODLY: Design Verilated with '--no-sched-zero-delay', but #0 delay executed at runtime");
    }
    return (__VinactExecute);
}

void Vsim___024root___trigger_clear__act(VlUnpacked<QData/*63:0*/, 1> &out) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vsim___024root___trigger_clear__act\n"); );
    // Locals
    IData/*31:0*/ n;
    // Body
    n = 0U;
    do {
        out[n] = 0ULL;
        n = ((IData)(1U) + n);
    } while ((1U > n));
}

bool Vsim___024root___eval_phase__nba(Vsim___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vsim___024root___eval_phase__nba\n"); );
    Vsim__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Locals
    CData/*0:0*/ __VnbaExecute;
    // Body
    __VnbaExecute = Vsim___024root___trigger_anySet__act(vlSelfRef.__VnbaTriggered);
    if (__VnbaExecute) {
        Vsim___024root___eval_nba(vlSelf);
        Vsim___024root___trigger_clear__act(vlSelfRef.__VnbaTriggered);
    }
    return (__VnbaExecute);
}

void Vsim___024root___eval(Vsim___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vsim___024root___eval\n"); );
    Vsim__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Locals
    IData/*31:0*/ __VnbaIterCount;
    // Body
    __VnbaIterCount = 0U;
    do {
        if (VL_UNLIKELY(((0x00002710U < __VnbaIterCount)))) {
#ifdef VL_DEBUG
            Vsim___024root___dump_triggers__act(vlSelfRef.__VnbaTriggered, "nba"s);
#endif
            VL_FATAL_MT("/workspace/.tmp_verilator/testbench.sv", 3, "", "DIDNOTCONVERGE: NBA region did not converge after '--converge-limit' of 10000 tries");
        }
        __VnbaIterCount = ((IData)(1U) + __VnbaIterCount);
        vlSelfRef.__VinactIterCount = 0U;
        do {
            if (VL_UNLIKELY(((0x00002710U < vlSelfRef.__VinactIterCount)))) {
                VL_FATAL_MT("/workspace/.tmp_verilator/testbench.sv", 3, "", "DIDNOTCONVERGE: Inactive region did not converge after '--converge-limit' of 10000 tries");
            }
            vlSelfRef.__VinactIterCount = ((IData)(1U) 
                                           + vlSelfRef.__VinactIterCount);
            vlSelfRef.__VactIterCount = 0U;
            do {
                if (VL_UNLIKELY(((0x00002710U < vlSelfRef.__VactIterCount)))) {
#ifdef VL_DEBUG
                    Vsim___024root___dump_triggers__act(vlSelfRef.__VactTriggered, "act"s);
#endif
                    VL_FATAL_MT("/workspace/.tmp_verilator/testbench.sv", 3, "", "DIDNOTCONVERGE: Active region did not converge after '--converge-limit' of 10000 tries");
                }
                vlSelfRef.__VactIterCount = ((IData)(1U) 
                                             + vlSelfRef.__VactIterCount);
                vlSelfRef.__VactPhaseResult = Vsim___024root___eval_phase__act(vlSelf);
            } while (vlSelfRef.__VactPhaseResult);
            vlSelfRef.__VinactPhaseResult = Vsim___024root___eval_phase__inact(vlSelf);
        } while (vlSelfRef.__VinactPhaseResult);
        vlSelfRef.__VnbaPhaseResult = Vsim___024root___eval_phase__nba(vlSelf);
    } while (vlSelfRef.__VnbaPhaseResult);
}

#ifdef VL_DEBUG
void Vsim___024root___eval_debug_assertions(Vsim___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vsim___024root___eval_debug_assertions\n"); );
    Vsim__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
}
#endif  // VL_DEBUG
