// Define and decompile the PoE recovery functions recovered from the FastIron
// 08.0.30u symbol table. Run only against the derived code segment at its
// original 0x20000000 load address.
//@category Brocade

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.SourceType;

public class DefinePoeFunctions extends GhidraScript {

    private record FunctionSpec(String name, long address, long size) {}

    private final FunctionSpec[] targets = {
        new FunctionSpec("poedevProcess1stSysStatusMsg", 0x2096e360L, 0xa40L),
        new FunctionSpec("pdsinePollResetResponse", 0x20972820L, 0x184L),
        new FunctionSpec("poedevProcessResetCompletion", 0x209730e0L, 0x2f8L),
        new FunctionSpec("pdsineResetHard", 0x209736e0L, 0xdcL),
        new FunctionSpec("pdsineProcessSwVersionCompletion", 0x209793c0L, 0x494L),
        new FunctionSpec("poedevIsDeviceFaulty", 0x20981640L, 0x38L),
        new FunctionSpec("poedevCleanup", 0x20970680L, 0x1e4L),
    };

    @Override
    public void run() throws Exception {
        DecompInterface decompiler = new DecompInterface();
        decompiler.setOptions(new DecompileOptions());
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException(decompiler.getLastMessage());
        }

        try {
            for (FunctionSpec spec : targets) {
                Address start = toAddr(spec.address());
                disassemble(start);
                Function function = currentProgram.getFunctionManager().getFunctionAt(start);
                if (function == null) {
                    function = currentProgram.getFunctionManager().createFunction(
                        spec.name(), start, new AddressSet(start, start.add(spec.size() - 1)),
                        SourceType.USER_DEFINED);
                }
                if (function == null) {
                    println("Unable to create " + spec.name());
                    continue;
                }
                function.setComment("Recovered from FastIron 08.0.30u symbol table.");
                DecompileResults result = decompiler.decompileFunction(function, 60, monitor);
                println("\n===== " + spec.name() + " @ " + start + " =====");
                if (result.decompileCompleted()) {
                    println(result.getDecompiledFunction().getC());
                }
                else {
                    println("Decompiler error: " + result.getErrorMessage());
                }
            }
        }
        finally {
            decompiler.dispose();
        }
    }
}
