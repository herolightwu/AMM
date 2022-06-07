import os

from pyteal import *


class MasterContract:
    class Vars:
        gov_key = Bytes("gov")
        pool_id_key = Bytes("pid")

    def on_create(self):
        return Seq(
            App.globalPut(self.Vars.pool_id_key, Txn.applications[1]),
            App.globalPut(self.Vars.gov_key, Txn.sender()),
            Approve()
        )
        
    def on_set_govener(self):
        #pool_id = App.globalGet(self.Vars.pool_id_key)
        account = Txn.accounts[1]
        pool_key_var = ScratchVar(TealType.bytes)
        has_pool = App.globalGetEx(Int(0), pool_key_var.load())
        asset_a = Txn.assets[0]
        asset_b = Txn.assets[1]
        pool_app_id = Txn.applications[1]
        return Seq(
            Assert(
                asset_a < asset_b
            ),
            pool_key_var.store(
                Concat(Itob(asset_a), Bytes("_"), Itob(asset_b))
            ),
            has_pool,
            Assert(
                has_pool.value() == pool_app_id
            ),
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields({
                TxnField.type_enum: TxnType.ApplicationCall,
                TxnField.on_completion: OnComplete.NoOp,
                TxnField.application_id: pool_app_id,
                TxnField.application_args: [Bytes("update")],
                TxnField.accounts:[account]
            }),
            InnerTxnBuilder.Submit(),
            Approve()
        )

    def on_new_pool(self):
        pool_id = App.globalGet(self.Vars.pool_id_key)
        pool_key_var = ScratchVar(TealType.bytes)
        has_pool = App.globalGetEx(Int(0), pool_key_var.load())
        pool_approval = AppParam.approvalProgram(Txn.applications[1])
        pool_clear = AppParam.clearStateProgram(Txn.applications[1])
        asset_a = Txn.assets[0]
        asset_b = Txn.assets[1]
        app_id = ScratchVar(TealType.uint64)
        return Seq(
            Assert(
                And(
                    pool_id == Txn.applications[1],
                    asset_a < asset_b
                )
            ),
            pool_key_var.store(
                Concat(Itob(asset_a), Bytes("_"), Itob(asset_b))
            ),
            has_pool,
            pool_approval,
            pool_clear,
            If(Not(has_pool.hasValue())).Then(Seq(
                InnerTxnBuilder.Begin(),
                InnerTxnBuilder.SetFields({
                    TxnField.type_enum: TxnType.ApplicationCall,
                    TxnField.on_completion: OnComplete.NoOp,
                    TxnField.approval_program: pool_approval.value(),
                    TxnField.clear_state_program: pool_clear.value(),
                    TxnField.global_num_uints: Int(32),
                    TxnField.global_num_byte_slices: Int(32),
                    TxnField.local_num_uints: Int(0),
                    TxnField.local_num_byte_slices: Int(0)
                }),
                InnerTxnBuilder.Submit(),
                
                app_id.store(InnerTxn.created_application_id()),
                
                InnerTxnBuilder.Begin(),
                InnerTxnBuilder.SetFields({
                    TxnField.type_enum: TxnType.ApplicationCall,
                    TxnField.on_completion: OnComplete.NoOp,
                    TxnField.application_id: InnerTxn.created_application_id(),
                    TxnField.application_args: [Bytes("set")],
                    TxnField.assets: [asset_a, asset_b]
                }),
                InnerTxnBuilder.Submit(),
                
                App.globalPut(
                    pool_key_var.load(),
                    app_id.load()
                )
                
            )),
            Approve()
        )

    def on_call(self):
        on_call_method = Txn.application_args[0]
        return Cond(
            [on_call_method == Bytes("new_pool"), self.on_new_pool()],
            [on_call_method == Bytes("set_govener"), self.on_set_govener()],
        )

    def approval_program(self):
        gov = App.globalGet(self.Vars.gov_key)
        return Cond(
            [Txn.application_id() == Int(0), self.on_create()],
            [
                Or(
                    Txn.on_completion() == OnComplete.OptIn,
                    Txn.on_completion() == OnComplete.CloseOut
                ),
                Reject()
            ],
            [
                Or(
                    Txn.on_completion() == OnComplete.UpdateApplication,
                    Txn.on_completion() == OnComplete.DeleteApplication
                ),
                Return(Txn.sender() == gov)
            ],
            [Txn.on_completion() == OnComplete.NoOp, self.on_call()],
        )

    def clear_program(self):
        return Approve()


if __name__ == "__main__":
    path = os.path.dirname(os.path.abspath(__file__))

    contract = MasterContract()

    with open(os.path.join(path, "master_approval.teal"), "w") as f:
        compiled = compileTeal(
            contract.approval_program(),
            mode=Mode.Application, version=6
        )
        f.write(compiled)

    with open(os.path.join(path, "master_clear.teal"), "w") as f:
        compiled = compileTeal(
            contract.clear_program(),
            mode=Mode.Application, version=6
        )
        f.write(compiled)
