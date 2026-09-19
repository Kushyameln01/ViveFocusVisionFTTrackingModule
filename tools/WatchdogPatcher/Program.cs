using Mono.Cecil;
using Mono.Cecil.Cil;

if (args.Length != 1)
{
    Console.Error.WriteLine("Usage: WatchdogPatcher <ViveFocusVisionFTTrackingModule.dll>");
    return 2;
}

var path = Path.GetFullPath(args[0]);
var assembly = AssemblyDefinition.ReadAssembly(path, new ReaderParameters { ReadWrite = false });
var module = assembly.MainModule;
var type = module.Types.FirstOrDefault(t => t.FullName == "ViveStreamingFaceTrackingModule.ViveStreamingFaceTrackingModule")
    ?? throw new InvalidOperationException("Target module type was not found.");

if (type.Fields.Any(f => f.Name == "LastEyeDataTimestampMs") ||
    type.Methods.Any(m => m.Name == "CheckFaceTrackingWatchdog"))
{
    throw new InvalidOperationException("Watchdog patch appears to be already applied.");
}

var hasClientConnection = type.Fields.Single(f => f.Name == "HasClientConnection");
var eyeTrackerInited = type.Fields.Single(f => f.Name == "EyeTrackerInited");
var lipTrackerInited = type.Fields.Single(f => f.Name == "LipTrackerInited");
var stopFaceTracking = type.Methods.Single(m => m.Name == "StopFaceTracking" && !m.HasParameters);
var update = type.Methods.Single(m => m.Name == "Update" && !m.HasParameters);
var statusCallback = type.Methods.Single(m => m.Name == "OnVSStatusUpdate");

var int64Type = module.TypeSystem.Int64;
var lastEye = new FieldDefinition("LastEyeDataTimestampMs",
    FieldAttributes.Private | FieldAttributes.Static, int64Type);
var lastLip = new FieldDefinition("LastLipDataTimestampMs",
    FieldAttributes.Private | FieldAttributes.Static, int64Type);
type.Fields.Add(lastEye);
type.Fields.Add(lastLip);

var tickCount64Getter = typeof(Environment).GetProperty(nameof(Environment.TickCount64))!.GetMethod!;
var getTickCount64 = module.ImportReference(tickCount64Getter);

var watchdog = new MethodDefinition("CheckFaceTrackingWatchdog",
    MethodAttributes.Private | MethodAttributes.Static | MethodAttributes.HideBySig,
    module.TypeSystem.Void);
type.Methods.Add(watchdog);
watchdog.Body.InitLocals = true;
var nowVar = new VariableDefinition(int64Type);
watchdog.Body.Variables.Add(nowVar);
var il = watchdog.Body.GetILProcessor();

var checkEye = Instruction.Create(OpCodes.Nop);
var checkLip = Instruction.Create(OpCodes.Nop);
var restart = Instruction.Create(OpCodes.Nop);
var done = Instruction.Create(OpCodes.Ret);

il.Append(Instruction.Create(OpCodes.Ldsfld, hasClientConnection));
il.Append(Instruction.Create(OpCodes.Brtrue_S, checkEye));
il.Append(Instruction.Create(OpCodes.Ret));

il.Append(checkEye);
il.Append(Instruction.Create(OpCodes.Call, getTickCount64));
il.Append(Instruction.Create(OpCodes.Stloc, nowVar));

il.Append(Instruction.Create(OpCodes.Ldsfld, eyeTrackerInited));
il.Append(Instruction.Create(OpCodes.Brfalse_S, checkLip));
il.Append(Instruction.Create(OpCodes.Ldsfld, lastEye));
il.Append(Instruction.Create(OpCodes.Ldc_I4_0));
il.Append(Instruction.Create(OpCodes.Conv_I8));
il.Append(Instruction.Create(OpCodes.Ceq));
il.Append(Instruction.Create(OpCodes.Brtrue_S, checkLip));
il.Append(Instruction.Create(OpCodes.Ldloc, nowVar));
il.Append(Instruction.Create(OpCodes.Ldsfld, lastEye));
il.Append(Instruction.Create(OpCodes.Sub));
il.Append(Instruction.Create(OpCodes.Ldc_I4, 5000));
il.Append(Instruction.Create(OpCodes.Conv_I8));
il.Append(Instruction.Create(OpCodes.Cgt));
il.Append(Instruction.Create(OpCodes.Brtrue_S, restart));

il.Append(checkLip);
il.Append(Instruction.Create(OpCodes.Ldsfld, lipTrackerInited));
il.Append(Instruction.Create(OpCodes.Brfalse_S, done));
il.Append(Instruction.Create(OpCodes.Ldsfld, lastLip));
il.Append(Instruction.Create(OpCodes.Ldc_I4_0));
il.Append(Instruction.Create(OpCodes.Conv_I8));
il.Append(Instruction.Create(OpCodes.Ceq));
il.Append(Instruction.Create(OpCodes.Brtrue_S, done));
il.Append(Instruction.Create(OpCodes.Ldloc, nowVar));
il.Append(Instruction.Create(OpCodes.Ldsfld, lastLip));
il.Append(Instruction.Create(OpCodes.Sub));
il.Append(Instruction.Create(OpCodes.Ldc_I4, 5000));
il.Append(Instruction.Create(OpCodes.Conv_I8));
il.Append(Instruction.Create(OpCodes.Cgt));
il.Append(Instruction.Create(OpCodes.Brfalse_S, done));

il.Append(restart);
il.Append(Instruction.Create(OpCodes.Call, stopFaceTracking));
il.Append(Instruction.Create(OpCodes.Ldc_I4_0));
il.Append(Instruction.Create(OpCodes.Conv_I8));
il.Append(Instruction.Create(OpCodes.Stsfld, lastEye));
il.Append(Instruction.Create(OpCodes.Ldc_I4_0));
il.Append(Instruction.Create(OpCodes.Conv_I8));
il.Append(Instruction.Create(OpCodes.Stsfld, lastLip));
il.Append(done);

void InsertTimestampAfterFlag(string flagName, FieldDefinition timestampField)
{
    var body = statusCallback.Body;
    var processor = body.GetILProcessor();
    var flagStore = body.Instructions.FirstOrDefault(i =>
        i.OpCode == OpCodes.Stsfld &&
        i.Operand is FieldReference f &&
        f.Name == flagName)
        ?? throw new InvalidOperationException($"Could not locate {flagName} assignment.");

    var callNow = Instruction.Create(OpCodes.Call, getTickCount64);
    var storeTimestamp = Instruction.Create(OpCodes.Stsfld, timestampField);
    processor.InsertAfter(flagStore, callNow);
    processor.InsertAfter(callNow, storeTimestamp);
}

InsertTimestampAfterFlag("EyeTrackerInited", lastEye);
InsertTimestampAfterFlag("LipTrackerInited", lastLip);

var updateIl = update.Body.GetILProcessor();
var startCall = update.Body.Instructions.FirstOrDefault(i =>
    (i.OpCode == OpCodes.Call || i.OpCode == OpCodes.Callvirt) &&
    i.Operand is MethodReference m &&
    m.Name == "StartFaceTracking")
    ?? throw new InvalidOperationException("Could not locate StartFaceTracking() call in Update().");
updateIl.InsertBefore(startCall, Instruction.Create(OpCodes.Call, watchdog));

assembly.Write(path);

using var verify = AssemblyDefinition.ReadAssembly(path);
var verifyType = verify.MainModule.Types.Single(t => t.FullName == type.FullName);
if (!verifyType.Fields.Any(f => f.Name == "LastEyeDataTimestampMs") ||
    !verifyType.Fields.Any(f => f.Name == "LastLipDataTimestampMs") ||
    !verifyType.Methods.Any(m => m.Name == "CheckFaceTrackingWatchdog"))
{
    throw new InvalidOperationException("Watchdog patch verification failed.");
}

Console.WriteLine("Applied 5-second Eye/Lip callback watchdog.");
Console.WriteLine("No FaceData mapping or native SDK library was modified.");
return 0;
